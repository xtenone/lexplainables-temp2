"""Begrensde LLM-stappen voor de RegelSpraak-vervolgfase.

Spiegelt engine/steps.py: elke stap doet één begrensde LLM-taak ("geef JSON conform schema") en
merge't de output tot de ronde-`model.json`-vorm (zie regelspraak/references/review-checkpoints.md).
De herkomst-velden komen van het LLM (naar de wetsanalyse-begrippen/-regels); de orchestrator bewaakt
de lus en de state.
"""

from __future__ import annotations

from ..llm.base import LLMClient, LLMResult
from . import regelspraak_prompts as rp


def _prov(activiteit: str, ronde: int, res: LLMResult, prompt_hash: str, basis: dict) -> dict:
    return {
        "activiteit": activiteit,
        "ronde": ronde,
        "model": res.model,
        "provider": res.provider,
        "output_strategie": res.output_strategie,
        "referentie_hash": rp.REGELSPRAAK_REFERENTIE_HASH,
        "prompt_hash": prompt_hash,
        "mcp_bwbid": basis.get("bwbId", ""),
        "mcp_versiedatum": basis.get("versiedatum", ""),
        "mcp_bronreferentie": basis.get("bronreferentie", ""),
        "tokens_in": res.tokens_in,
        "tokens_out": res.tokens_out,
        "cache_read_in": res.cache_read_in,
        "cache_write_in": res.cache_write_in,
    }


def _merge_validatiepunten(oud: list, nieuw: list) -> list:
    """Union van validatiepunten (lijst van strings) met behoud van volgorde en ontdubbeling.
    Bij een revise herhaalt het LLM eerdere interpretatie-/twijfelsignalen niet altijd; die mogen niet
    stil verdwijnen. Niet-hashbare punten (bv. dicts) worden best-effort op repr ontdubbeld."""
    gezien: set = set()
    samen: list = []
    for punt in [*(oud or []), *(nieuw or [])]:
        sleutel = punt if isinstance(punt, str) else repr(punt)
        if sleutel in gezien:
            continue
        gezien.add(sleutel)
        samen.append(punt)
    return samen


def _prov_basis(context: dict) -> dict:
    bronnen = context.get("bronnen") or []
    b = bronnen[0] if bronnen else {}
    return {
        "bwbId": b.get("bwbId", ""),
        "versiedatum": b.get("versiedatum", ""),
        "bronreferentie": b.get("bronreferentie", ""),
    }


def gegevensspraak_index(gegevensspraak: dict) -> dict:
    """Lichte index (id → leesbare naam) zodat de regel-review/validatie naar het objectmodel
    kan verwijzen. Spiegelt het `gegevensspraak_index`-veld uit de skill."""
    gs = gegevensspraak or {}
    return {
        "objecttypen": [
            {"id": o.get("id", ""), "naam": o.get("naam", "")}
            for o in (gs.get("objecttypen") or [])
        ],
        "parameters": [
            {"id": p.get("id", ""), "naam": p.get("naam", "")}
            for p in (gs.get("parameters") or [])
        ],
        "feittypen": [
            {"id": f.get("id", ""), "naam": f.get("naam", ""),
             "rollen": [r.get("naam", "") for r in (f.get("rollen") or [])]}
            for f in (gs.get("feittypen") or [])
        ],
    }


async def genereer_gegevens(llm: LLMClient, ronde: int, context: dict) -> tuple[dict, dict]:
    """Stap 2 (GegevensSpraak) — bouw het objectmodel uit de rapport-context."""
    system, user, schema, phash = rp.gegevens_prompt(context)
    res = await llm.complete(system, user, schema)
    model = {
        "werkgebied": context.get("werkgebied") or {},
        "gegevensspraak": res.data or {},
    }
    return model, _prov("rs-gegevens", ronde, res, phash, _prov_basis(context))


async def genereer_regels(llm: LLMClient, ronde: int, context: dict) -> tuple[dict, dict]:
    """Stap 3 (RegelSpraak-regels) — schrijf de regels bovenop het objectmodel uit `context`."""
    system, user, schema, phash = rp.regels_prompt(context)
    res = await llm.complete(system, user, schema)
    model = {
        "werkgebied": context.get("werkgebied") or {},
        "gegevensspraak_index": gegevensspraak_index(context.get("gegevensspraak") or {}),
        "regels": (res.data or {}).get("regels", []),
        "validatiepunten": (res.data or {}).get("validatiepunten", []),
    }
    return model, _prov("rs-regels", ronde, res, phash, _prov_basis(context))


async def herzie(
    llm: LLMClient, stap: str, ronde: int, context: dict, vorige: dict, feedback: dict
) -> tuple[dict, dict]:
    """Herzie GegevensSpraak (stap='rs-gegevens') of de regels (stap='rs-regels') op feedback."""
    system, user, schema, phash = rp.revise_prompt(stap, vorige, feedback)
    res = await llm.complete(system, user, schema)
    if stap == "rs-gegevens":
        model = {
            "werkgebied": context.get("werkgebied") or vorige.get("werkgebied") or {},
            "gegevensspraak": res.data or {},
        }
    else:
        model = {
            "werkgebied": context.get("werkgebied") or vorige.get("werkgebied") or {},
            "gegevensspraak_index": gegevensspraak_index(context.get("gegevensspraak") or {}),
            "regels": (res.data or {}).get("regels", []),
            # Behoud de validatiepunten van de vorige ronde (twijfel-/interpretatiesignalen): mergen
            # i.p.v. vervangen, zodat een revise die ze niet herhaalt ze niet stil weggooit.
            "validatiepunten": _merge_validatiepunten(
                vorige.get("validatiepunten") or [], (res.data or {}).get("validatiepunten", [])
            ),
        }
    return model, _prov(stap, ronde, res, phash, _prov_basis(context))
