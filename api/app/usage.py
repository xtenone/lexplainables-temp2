"""Token-verbruik-aggregatie over de `provenance` van alle projecten.

Read-only: er is geen aparte tracking-laag nodig. Elke project-`provenance[]` bevat per ronde het
feitelijk gebruikte model/provider en `tokens_in`/`tokens_out` (zie contracts.RondeProvenance),
gevuld vanuit het LLMResult in engine/steps. We laden de provenance-kolommen en aggregeren in
Python — portable over de DB-backend heen en ruim voldoende voor dit datavolume.
"""

from __future__ import annotations

from sqlalchemy import select

from . import db

# Toegestane groepeer-sleutels → waar de waarde vandaan komt. `model`/`provider` zitten op de
# provenance-ronde; `model_profile`/`client_id` op het project zelf.
_PROV_VELDEN = {"model", "provider"}
_PROJECT_VELDEN = {"model_profile", "client_id"}
_GROUP_VELDEN = _PROV_VELDEN | _PROJECT_VELDEN


async def usage_report(
    group_by: str = "model", van: str | None = None, tot: str | None = None
) -> dict:
    """Geef het verbruik gegroepeerd op `group_by`, plus een grand total.

    `van`/`tot` filteren (inclusief/exclusief) op `provenance.tijdstip` (ISO-string, lexicografisch
    vergelijkbaar). Geeft `{"group_by", "rows": [...], "totaal": {...}}`.
    """
    if group_by not in _GROUP_VELDEN:
        raise ValueError(f"Onbekende group_by: {group_by!r} (kies uit {sorted(_GROUP_VELDEN)})")

    async with db.get_engine().connect() as conn:
        rijen = (await conn.execute(select(
            db.projects.c.slug,
            db.projects.c.model_profile,
            db.projects.c.client_id,
            db.projects.c.provenance,
        ))).mappings().all()

    # sleutel → {tokens_in, tokens_out, rondes, analyses(set van slugs)}
    groepen: dict[str, dict] = {}
    for rij in rijen:
        project_sleutel = rij[group_by] if group_by in _PROJECT_VELDEN else None
        for prov in rij["provenance"] or []:
            tijdstip = prov.get("tijdstip", "")
            if van and tijdstip < van:
                continue
            if tot and tijdstip >= tot:
                continue
            sleutel = project_sleutel if group_by in _PROJECT_VELDEN else (prov.get(group_by) or "")
            g = groepen.setdefault(
                sleutel or "",
                {"tokens_in": 0, "tokens_out": 0, "cache_read_in": 0, "cache_write_in": 0,
                 "rondes": 0, "analyses": set()},
            )
            g["tokens_in"] += prov.get("tokens_in", 0) or 0
            g["tokens_out"] += prov.get("tokens_out", 0) or 0
            # Prompt-cache-telemetrie (0 bij oudere rondes of caching uit): cache_read_in = uit de
            # cache geserveerd (~0.1× kosten), cache_write_in = vers geschreven (~1.25×).
            g["cache_read_in"] += prov.get("cache_read_in", 0) or 0
            g["cache_write_in"] += prov.get("cache_write_in", 0) or 0
            g["rondes"] += 1
            g["analyses"].add(rij["slug"])

    rows = [
        {
            "sleutel": sleutel,
            "tokens_in": g["tokens_in"],
            "tokens_out": g["tokens_out"],
            "cache_read_in": g["cache_read_in"],
            "cache_write_in": g["cache_write_in"],
            "rondes": g["rondes"],
            "analyses": len(g["analyses"]),
        }
        for sleutel, g in groepen.items()
    ]
    rows.sort(key=lambda r: r["tokens_in"], reverse=True)
    totaal = {
        "tokens_in": sum(r["tokens_in"] for r in rows),
        "tokens_out": sum(r["tokens_out"] for r in rows),
        "cache_read_in": sum(r["cache_read_in"] for r in rows),
        "cache_write_in": sum(r["cache_write_in"] for r in rows),
        "rondes": sum(r["rondes"] for r in rows),
        "analyses": sum(r["analyses"] for r in rows),
    }
    return {"group_by": group_by, "rows": rows, "totaal": totaal}


async def usage_per_profiel() -> dict[str, dict]:
    """Verbruik gegroepeerd op `model_profile` als map name → totalen (voor de profielenlijst)."""
    rapport = await usage_report(group_by="model_profile")
    return {r["sleutel"]: r for r in rapport["rows"] if r["sleutel"]}
