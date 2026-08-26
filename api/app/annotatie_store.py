"""
AnnotatieStore — persistentie voor het annotatie-domein (los van de analyse-`JobStore`).

Zelfde SQLAlchemy-Core-stijl als `postgres_store.py` op dezelfde engine (`db.get_engine()`), maar een
eigen, verse tabelset. Het document draagt de HUIDIGE elementen-staat (JSON); `annotatie_audit` is de
append-only geschiedenis (alleen inserts). Tijd komt uit Python (`db.utcnow`) zodat de queries portable
blijven (SQLite-tests).
"""
from __future__ import annotations

from typing import Callable

from sqlalchemy import delete, insert, select, update

from . import db
from .annotatie_contracts import AgentRun, AnnotatieDocument, AnnotatieElement, AuditRecord

# Sentinel: het document bestaat (en is van de client) maar het gevraagde element niet.
GEEN_ELEMENT = object()
# Sentinel: de meegegeven `If-Match` komt niet overeen met de huidige staat (→ 412).
CONFLICT = object()


def etag_van(doc: AnnotatieDocument) -> str:
    """Zwakke ETag uit `updated`. Bewust geen aparte versiekolom: `updated` wordt binnen dezelfde
    transactie gezet als de elementen, dus het is even betrouwbaar en kost geen migratie."""
    return f'W/"{doc.updated.isoformat() if doc.updated else "0"}"'


def _naar_document(row) -> AnnotatieDocument:
    d = row._mapping
    return AnnotatieDocument(
        slug=d["slug"],
        user_id=d["user_id"] or "",   # legacy-rijen (vóór de migratie) hebben NULL → ""
        client_id=d["client_id"],
        citeertitel=d["citeertitel"] or "",
        werkgebied=d["werkgebied"],
        bwbId=d["bwbId"],
        artikel=d["artikel"],
        lid=d["lid"],
        status=d["status"],
        elementen=[AnnotatieElement.model_validate(e) for e in (d["elementen"] or [])],
        runs=[AgentRun.model_validate(r) for r in (d["runs"] or [])],
        created=db.aware(d["created"]),
        updated=db.aware(d["updated"]),
    )


class AnnotatieStore:
    async def maak_document(self, doc: AnnotatieDocument) -> None:
        now = db.utcnow()
        async with db.get_engine().begin() as conn:
            await conn.execute(insert(db.annotatie_documenten).values(
                slug=doc.slug,
                user_id=doc.user_id,
                client_id=doc.client_id,
                citeertitel=doc.citeertitel,
                werkgebied=doc.werkgebied,
                bwbId=doc.bwbId,
                artikel=doc.artikel,
                lid=doc.lid or "",
                status=doc.status.value,
                elementen=[e.model_dump(mode="json") for e in doc.elementen],
                runs=[r.model_dump(mode="json") for r in doc.runs],
                created=now,
                updated=now,
            ))

    async def laad_document(self, slug: str) -> AnnotatieDocument | None:
        async with db.get_engine().connect() as conn:
            row = (await conn.execute(
                select(db.annotatie_documenten).where(db.annotatie_documenten.c.slug == slug)
            )).first()
        return _naar_document(row) if row else None

    async def lijst_documenten(self, user_id: str, limit: int = 50, offset: int = 0) -> list[AnnotatieDocument]:
        async with db.get_engine().connect() as conn:
            rows = (await conn.execute(
                select(db.annotatie_documenten)
                .where(db.annotatie_documenten.c.user_id == user_id)
                .order_by(db.annotatie_documenten.c.updated.desc())
                .limit(limit).offset(offset)
            )).all()
        return [_naar_document(r) for r in rows]

    async def muteer_document(
        self,
        slug: str,
        user_id: str,
        muteer: Callable[[AnnotatieDocument], object | None],
        if_match: str | None = None,
    ) -> AnnotatieDocument | None | object:
        """Het ENIGE schrijfpad naar `elementen`, `runs` en `status`. Laadt met een row-lock, toetst
        eigenaarschap en `If-Match`, laat `muteer` het document herschikken en schrijft in DEZELFDE
        transactie weg.

        Eén pad met één slot, want twee gelijktijdige schrijvers op dezelfde JSON-kolom overschrijven
        elkaar anders volledig (lost update). Er stond hier eerder ook een `vervang_elementen` zónder
        lock; die is weg — een destructief pad dat blijft rondslingeren wordt vroeg of laat gebruikt.

        `muteer` mag een sentinel teruggeven (bv. `GEEN_ELEMENT`) om de mutatie af te breken; die komt
        dan ongewijzigd terug en er wordt niets geschreven. Retourneert verder het bijgewerkte
        document, `None` (onbekend of niet-eigenaar → 404) of `CONFLICT` (ETag-mismatch → 412).
        Op SQLite is `with_for_update` een no-op, maar serialiseert de transactie de schrijfactie.
        """
        now = db.utcnow()
        async with db.get_engine().begin() as conn:
            row = (await conn.execute(
                select(db.annotatie_documenten)
                .where(db.annotatie_documenten.c.slug == slug)
                .with_for_update()
            )).first()
            if row is None:
                return None
            doc = _naar_document(row)
            if doc.user_id != user_id:
                return None
            if if_match is not None and if_match != etag_van(doc):
                return CONFLICT
            uitkomst = muteer(doc)
            if uitkomst is not None:
                return uitkomst
            await conn.execute(
                update(db.annotatie_documenten)
                .where(db.annotatie_documenten.c.slug == slug)
                .values(
                    elementen=[e.model_dump(mode="json") for e in doc.elementen],
                    runs=[r.model_dump(mode="json") for r in doc.runs],
                    status=doc.status.value,
                    updated=now,
                )
            )
        doc.updated = now
        return doc

    async def beslis_op_element(
        self,
        slug: str,
        user_id: str,
        element_id: str,
        toepassen: Callable[[AnnotatieDocument, AnnotatieElement], object | None],
    ) -> AnnotatieDocument | None | object:
        """Pas een human-decision atomair toe op één element. Dunne wrapper om `muteer_document`.

        `toepassen` krijgt het hele document mee — de vraag óf er beslist mag worden hangt niet
        alleen van het element af maar ook van de documentstatus, en die toets hoort binnen dezelfde
        row-lock als de mutatie. Geeft het een sentinel terug (bv. `CONFLICT`), dan wordt er niets
        geschreven en komt die sentinel ongewijzigd terug.
        """

        def muteer(doc: AnnotatieDocument):
            el = next((x for x in doc.elementen if x.id == element_id), None)
            if el is None:
                return GEEN_ELEMENT
            return toepassen(doc, el)

        return await self.muteer_document(slug, user_id, muteer)

    async def verwijder_document(self, slug: str) -> None:
        async with db.get_engine().begin() as conn:
            await conn.execute(delete(db.annotatie_audit).where(db.annotatie_audit.c.document_slug == slug))
            await conn.execute(delete(db.annotatie_documenten).where(db.annotatie_documenten.c.slug == slug))

    async def schrijf_audit(
        self, slug: str, client_id: str, actor: str, actie: str,
        element_id: str | None = None, detail: dict | None = None,
    ) -> None:
        """Append-only: voegt één auditregel toe (nooit update/delete)."""
        async with db.get_engine().begin() as conn:
            await conn.execute(insert(db.annotatie_audit).values(
                document_slug=slug, client_id=client_id, actor=actor, actie=actie,
                element_id=element_id, detail=detail or {}, tijdstip=db.utcnow(),
            ))

    async def schrijf_auditregels(self, slug: str, client_id: str, actor: str, regels: list[tuple]) -> None:
        """Meerdere auditregels in één insert: `[(actie, element_id, detail), …]`.

        Een agent-ronde raakt tientallen elementen; per regel een aparte transactie openen zou de
        schrijfactie onnodig oprekken en het log kunnen laten scheuren als er halverwege iets misgaat.
        """
        if not regels:
            return
        nu = db.utcnow()
        async with db.get_engine().begin() as conn:
            await conn.execute(insert(db.annotatie_audit), [
                {
                    "document_slug": slug, "client_id": client_id, "actor": actor,
                    "actie": actie, "element_id": element_id, "detail": detail or {}, "tijdstip": nu,
                }
                for actie, element_id, detail in regels
            ])

    async def lees_audit(self, slug: str, limit: int = 200, offset: int = 0) -> list[AuditRecord]:
        async with db.get_engine().connect() as conn:
            rows = (await conn.execute(
                select(db.annotatie_audit)
                .where(db.annotatie_audit.c.document_slug == slug)
                .order_by(db.annotatie_audit.c.id)
                .limit(limit).offset(offset)
            )).all()
        return [
            AuditRecord(
                id=r._mapping["id"], actor=r._mapping["actor"], actie=r._mapping["actie"],
                element_id=r._mapping["element_id"], detail=r._mapping["detail"] or {},
                tijdstip=db.aware(r._mapping["tijdstip"]),
            )
            for r in rows
        ]
