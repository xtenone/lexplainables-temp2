"""GesprekStore — persistentie voor het gesprekken-domein (chatgeschiedenis van de werkplek),
werkwijze-ADR-0007.

Zelfde SQLAlchemy-Core-stijl als het annotatie-domein op dezelfde engine, met een eigen tabelset
(`gesprekken` + `gesprek_berichten`). Per-gebruiker gescopet (`user_id`). De berichten staan als
aparte, geordende rijen; de heterogene beurt-payload zit in de JSON-kolom `inhoud`. Tijd komt uit
Python (`shared.db.utcnow`) zodat de queries portable blijven (SQLite-tests).
"""

from __future__ import annotations

from sqlalchemy import delete, func, insert, select, update

from ...shared.db import aware, get_engine, utcnow
from .models import Bericht, BerichtInvoer, Gesprek, GesprekSamenvatting, gesprek_berichten, gesprekken


def _bericht_uit_row(row) -> Bericht:
    d = row._mapping
    inhoud = d["inhoud"] or {}
    return Bericht(
        id=d["id"],
        rol=d["rol"],
        tekst=inhoud.get("tekst", ""),
        denk=inhoud.get("denk", ""),
        bronnen=inhoud.get("bronnen", []) or [],
        annotatie_slug=inhoud.get("annotatie_slug", ""),
        annotatie_titel=inhoud.get("annotatie_titel", ""),
        run_id=inhoud.get("run_id", ""),
        ontbrekend=inhoud.get("ontbrekend", []) or [],
        created=aware(d["created"]),
    )


def _inhoud(inv: BerichtInvoer | Bericht) -> dict:
    """De heterogene beurt-payload → de JSON-kolom (weglaten wat leeg is houdt de rij compact)."""
    inhoud: dict = {"tekst": inv.tekst}
    if inv.denk:
        inhoud["denk"] = inv.denk
    if inv.bronnen:
        inhoud["bronnen"] = inv.bronnen
    if inv.annotatie_slug:
        inhoud["annotatie_slug"] = inv.annotatie_slug
    if inv.annotatie_titel:
        inhoud["annotatie_titel"] = inv.annotatie_titel
    if inv.ontbrekend:
        inhoud["ontbrekend"] = inv.ontbrekend
    if inv.run_id:
        inhoud["run_id"] = inv.run_id
    return inhoud


class GesprekStore:
    async def maak_gesprek(self, gesprek: Gesprek) -> None:
        now = utcnow()
        async with get_engine().begin() as conn:
            await conn.execute(insert(gesprekken).values(
                id=gesprek.id,
                user_id=gesprek.user_id,
                titel=gesprek.titel,
                created=now,
                updated=now,
            ))

    async def laad_gesprek(self, gesprek_id: str) -> Gesprek | None:
        async with get_engine().connect() as conn:
            row = (await conn.execute(
                select(gesprekken).where(gesprekken.c.id == gesprek_id)
            )).first()
            if row is None:
                return None
            berichten = (await conn.execute(
                select(gesprek_berichten)
                .where(gesprek_berichten.c.gesprek_id == gesprek_id)
                .order_by(gesprek_berichten.c.id)
            )).all()
        d = row._mapping
        return Gesprek(
            id=d["id"],
            user_id=d["user_id"],
            titel=d["titel"],
            berichten=[_bericht_uit_row(b) for b in berichten],
            created=aware(d["created"]),
            updated=aware(d["updated"]),
        )

    async def lijst_samenvattingen(
        self, user_id: str, limit: int = 100, offset: int = 0
    ) -> list[GesprekSamenvatting]:
        aantal = func.count(gesprek_berichten.c.id).label("aantal")
        async with get_engine().connect() as conn:
            rows = (await conn.execute(
                select(gesprekken, aantal)
                .select_from(gesprekken.outerjoin(
                    gesprek_berichten,
                    gesprekken.c.id == gesprek_berichten.c.gesprek_id,
                ))
                .where(gesprekken.c.user_id == user_id)
                .group_by(gesprekken.c.id)
                .order_by(gesprekken.c.updated.desc())
                .limit(limit).offset(offset)
            )).all()
        return [
            GesprekSamenvatting(
                id=r._mapping["id"],
                titel=r._mapping["titel"],
                aantal_berichten=r._mapping["aantal"],
                updated=aware(r._mapping["updated"]),
            )
            for r in rows
        ]

    @staticmethod
    async def _bericht_van_run(conn, gesprek_id: str, run_id: str) -> Bericht | None:
        """Staat de uitkomst van deze run er al? Kijkt alleen naar de staart van het gesprek: een
        run schrijft aan het eind van zijn eigen beurt, dus verder terug zoeken heeft geen zin."""
        rows = (await conn.execute(
            select(gesprek_berichten)
            .where(gesprek_berichten.c.gesprek_id == gesprek_id)
            .order_by(gesprek_berichten.c.id.desc())
            .limit(20)
        )).fetchall()
        for row in rows:
            if (row._mapping["inhoud"] or {}).get("run_id") == run_id:
                return _bericht_uit_row(row)
        return None

    async def voeg_bericht_toe(self, gesprek_id: str, inv: BerichtInvoer) -> Bericht:
        """Voeg één beurt toe. Append-only, behalve dat een `run_id` maar één keer mag landen.

        Die uitzondering is er omdat een agent-run niet meer aan één browserverbinding hangt: er
        kunnen meerdere tabbladen op dezelfde run meekijken, en die zouden anders elk hun eigen kopie
        van hetzelfde antwoord wegschrijven. De controle staat bewust ín dezelfde transactie als de
        insert. Er is géén unieke index: `reconcile_schema` voegt op bestaande tabellen alleen
        kolommen toe, en de index op (gesprek_id, id) maakt deze check goedkoop.

        Let op de aanname: dit werkt omdat er per run feitelijk één schrijver tegelijk is. Komt er
        ooit een tweede API-replica die gelijktijdig dezelfde run afrondt, dan is check-then-insert
        niet meer genoeg en moet er een unieke constraint bij.
        """
        now = utcnow()
        async with get_engine().begin() as conn:
            if inv.run_id:
                bestaand = await self._bericht_van_run(conn, gesprek_id, inv.run_id)
                if bestaand is not None:
                    return bestaand
            result = await conn.execute(insert(gesprek_berichten).values(
                gesprek_id=gesprek_id,
                rol=inv.rol.value,
                inhoud=_inhoud(inv),
                created=now,
            ))
            # Bump het gesprek zodat de sidebar-sortering (updated desc) meeloopt.
            await conn.execute(
                update(gesprekken)
                .where(gesprekken.c.id == gesprek_id)
                .values(updated=now)
            )
            nieuw_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
        return Bericht(
            id=nieuw_id, rol=inv.rol, tekst=inv.tekst, denk=inv.denk, bronnen=inv.bronnen,
            annotatie_slug=inv.annotatie_slug, annotatie_titel=inv.annotatie_titel,
            ontbrekend=inv.ontbrekend, run_id=inv.run_id, created=aware(now),
        )

    async def hernoem_gesprek(self, gesprek_id: str, titel: str) -> None:
        async with get_engine().begin() as conn:
            await conn.execute(
                update(gesprekken)
                .where(gesprekken.c.id == gesprek_id)
                .values(titel=titel, updated=utcnow())
            )

    async def verwijder_gesprek(self, gesprek_id: str) -> None:
        async with get_engine().begin() as conn:
            await conn.execute(
                delete(gesprek_berichten).where(gesprek_berichten.c.gesprek_id == gesprek_id)
            )
            await conn.execute(delete(gesprekken).where(gesprekken.c.id == gesprek_id))
