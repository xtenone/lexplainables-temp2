"""Service-laag voor gebruikersfeedback.

Analisten en beheerders sturen feedback vanuit de webapp; beheerders lezen de ingezonden
feedback via /v1/admin/feedback. Elke rij is onwijzigbaar (append-only).

Bewust cross-tenant: net als users/profielen/wetcatalogus is de admin-laag hier NIET
per-client gescoped — een beheerder ziet feedback van alle clients. `client_id` wordt
getoond zodat dat voor de beheerder transparant is, niet om toegang te beperken.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, insert, select, update

from . import db


class FeedbackError(ValueError):
    """Ongeldige feedback-operatie (onbekend id)."""


async def dien_in(
    client_id: str,
    userid: str,
    categorie: str,
    tekst: str,
    pagina: str | None,
) -> int:
    """Sla een feedbackitem op en geef het id terug."""
    nu = db.utcnow()
    async with db.get_engine().begin() as conn:
        result = await conn.execute(
            insert(db.user_feedback)
            .values(
                client_id=client_id,
                userid=userid,
                categorie=categorie,
                tekst=tekst.strip(),
                pagina=pagina,
                created=nu,
            )
            .returning(db.user_feedback.c.id)
        )
        return result.scalar_one()


async def verwijder_feedback(feedback_id: int) -> None:
    """Verwijder één feedbackitem op id."""
    async with db.get_engine().begin() as conn:
        result = await conn.execute(
            delete(db.user_feedback).where(db.user_feedback.c.id == feedback_id)
        )
    if result.rowcount == 0:
        raise FeedbackError(f"Feedback {feedback_id} niet gevonden.")


async def ongelezen_feedback_aantal(admin_userid: str) -> int:
    """Aantal feedback-items ingediend nadat deze beheerder ze voor het laatst heeft gezien —
    of, voor een beheerder die nog nooit gekeken heeft, sinds zijn eigen registratie (niet
    alle historische feedback ooit)."""
    uf = db.user_feedback
    u = db.users
    gezien_of_created_subq = (
        select(func.coalesce(u.c.feedback_gezien_op, u.c.created))
        .where(u.c.userid == admin_userid)
        .scalar_subquery()
    )
    stmt = select(func.count()).select_from(uf).where(uf.c.created > gezien_of_created_subq)
    async with db.get_engine().connect() as conn:
        result = await conn.scalar(stmt)
    return int(result or 0)


async def markeer_feedback_gezien(admin_userid: str, tot: datetime | None = None) -> None:
    """Sla op tot welk tijdstip deze beheerder de feedback gezien heeft. Zonder `tot`
    (default, backward-compatibel) geldt het huidige moment; met een expliciete `tot`
    (de created-timestamp van het nieuwste getoonde item) kan de aanroeper voorkomen dat
    feedback die tussen het laden en het markeren binnenkomt ten onrechte als gezien telt."""
    async with db.get_engine().begin() as conn:
        await conn.execute(
            update(db.users)
            .where(db.users.c.userid == admin_userid)
            .values(feedback_gezien_op=tot or db.utcnow())
        )


async def lijst_feedback_totaal() -> int:
    """Totaal aantal ingezonden feedback-items, voor de admin-paginering."""
    async with db.get_engine().connect() as conn:
        result = await conn.scalar(select(func.count()).select_from(db.user_feedback))
    return int(result or 0)


async def lijst_feedback(offset: int = 0, limit: int = 50) -> list[dict]:
    """Alle ingezonden feedback, nieuwste eerst (voor beheerders)."""
    stmt = (
        select(db.user_feedback)
        .order_by(db.user_feedback.c.created.desc())
        .offset(offset)
        .limit(limit)
    )
    async with db.get_engine().connect() as conn:
        rows = (await conn.execute(stmt)).mappings().all()
    return [
        {
            "id":        r["id"],
            "client_id": r["client_id"],
            "userid":    r["userid"],
            "categorie": r["categorie"],
            "tekst":     r["tekst"],
            "pagina":    r["pagina"],
            "created":   db.aware(r["created"]),
        }
        for r in rows
    ]
