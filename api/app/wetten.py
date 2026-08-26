"""Service-laag over de wet-catalogus in de database.

CRUD voor `WetCatalogus` (gebruikt door de admin-router) plus `resolve_naam`: haal de officiële
citeertitel van een wet op via de MCP (`wettenbank_structuur`, vereist alleen een BWB-id), zodat de
beheer-UI de naam kan voorstellen. De catalogus is bewust niet-dwingend: hij valideert geen
analyses, maar levert alleen de keuzelijst voor de frontend-dropdown.
"""

from __future__ import annotations

from sqlalchemy import delete, insert, select, update

from . import db
from .config import Settings, get_settings
from .wet_catalog import WetCatalogus, _utcnow
from .wettenbank import WettenbankClient, WettenbankError


class WetError(ValueError):
    """Ongeldige catalogus-operatie (onbekende wet, e.d.)."""


def _row_to_wet(row) -> WetCatalogus:
    m = dict(row)
    return WetCatalogus(
        bwbId=m["bwbId"],
        naam=m["naam"] or "",
        updated_by=m["updated_by"] or "",
        created=db.aware(m["created"]),
        updated=db.aware(m["updated"]),
    )


# --- lezen ---------------------------------------------------------------------

async def list_wetten() -> list[WetCatalogus]:
    async with db.get_engine().connect() as conn:
        rows = (await conn.execute(
            select(db.wet_catalogus).order_by(db.wet_catalogus.c.naam)
        )).mappings().all()
    return [_row_to_wet(r) for r in rows]


async def get_wet(bwb_id: str) -> WetCatalogus | None:
    async with db.get_engine().connect() as conn:
        row = (await conn.execute(
            select(db.wet_catalogus).where(db.wet_catalogus.c.bwbId == bwb_id)
        )).mappings().first()
    return _row_to_wet(row) if row is not None else None


# --- muteren -------------------------------------------------------------------

async def upsert_wet(bwb_id: str, *, naam: str, updated_by: str) -> WetCatalogus:
    """Maak of werk een catalogus-item bij (de BWB-id is de sleutel)."""
    bestaand = await get_wet(bwb_id)
    now = _utcnow()
    async with db.get_engine().begin() as conn:
        if bestaand is None:
            await conn.execute(insert(db.wet_catalogus).values(
                bwbId=bwb_id, naam=naam, updated_by=updated_by, created=now, updated=now,
            ))
        else:
            await conn.execute(
                update(db.wet_catalogus).where(db.wet_catalogus.c.bwbId == bwb_id)
                .values(naam=naam, updated_by=updated_by, updated=now)
            )
    return WetCatalogus(
        bwbId=bwb_id, naam=naam, updated_by=updated_by,
        created=bestaand.created if bestaand else now, updated=now,
    )


async def delete_wet(bwb_id: str) -> None:
    if await get_wet(bwb_id) is None:
        raise WetError(f"Onbekende wet: {bwb_id!r}")
    async with db.get_engine().begin() as conn:
        await conn.execute(delete(db.wet_catalogus).where(db.wet_catalogus.c.bwbId == bwb_id))


# --- MCP-naamresolutie ---------------------------------------------------------

async def resolve_naam(bwb_id: str, settings: Settings | None = None) -> str:
    """Haal de officiële citeertitel op via de MCP. Werpt WettenbankError bij een mis."""
    s = settings or get_settings()
    data = await WettenbankClient(s).structuur(bwb_id)
    naam = data.get("citeertitel") or ""
    if not naam:
        raise WettenbankError(f"Geen citeertitel gevonden voor {bwb_id}")
    return naam
