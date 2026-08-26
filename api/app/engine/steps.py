"""Begrensde LLM-stappen. Elke stap mergt de brongetrouwe basis (uit de MCP) met de
cognitieve output van het LLM — de basis-velden worden nooit door het LLM verzonnen.

Activiteit 2 wordt **per bron** gegenereerd (`genereer_act2_bron`) en in de orchestrator tot
`bronnen[]` geaggregeerd. Activiteit 3 is **werkgebied-breed** en **twee-staps** binnen één
ronde: 3a levert de begrippen, 3b bouwt de regels MET die begrippen als bouwstenen (methode:
eerst een begrip voor wat de regel afleidt, dán de regel).
"""

from __future__ import annotations

import re

from ..llm.base import LLMClient, LLMResult
from . import prompts


def _prov(activiteit: str, ronde: int, res: LLMResult, prompt_hash: str, basis: dict) -> dict:
    return {
        "activiteit": activiteit,
        "ronde": ronde,
        "model": res.model,
        "provider": res.provider,
        "output_strategie": res.output_strategie,
        "referentie_hash": prompts.REFERENTIE_HASH,
        "prompt_hash": prompt_hash,
        "mcp_bwbid": basis.get("bwbId", ""),
        "mcp_versiedatum": basis.get("versiedatum", ""),
        "mcp_bronreferentie": basis.get("bronreferentie", ""),
        "tokens_in": res.tokens_in,
        "tokens_out": res.tokens_out,
        "cache_read_in": res.cache_read_in,
        "cache_write_in": res.cache_write_in,
    }


def _prov_basis(analyse: dict) -> dict:
    """Representatieve mcp-velden voor de provenance van een werkgebied-brede stap (eerste bron)."""
    bronnen = analyse.get("bronnen") or []
    b = bronnen[0] if bronnen else {}
    return {
        "bwbId": b.get("bwbId", ""),
        "versiedatum": b.get("versiedatum", ""),
        "bronreferentie": b.get("bronreferentie", ""),
    }


def _bron_index(analyse: dict) -> list[dict]:
    """Lichte bron-index (voor act-3 vindplaatsen): bron_id → label + identificatie."""
    return [
        {
            "bron_id": b.get("bron_id", ""),
            "label": b.get("label", ""),
            "bwbId": b.get("bwbId", ""),
            "artikel": b.get("artikel", ""),
            "lid": b.get("lid"),
        }
        for b in (analyse.get("bronnen") or [])
    ]


def _merge_bron(bron_basis: dict, out: dict) -> dict:
    """Bouw één bron-dict: brongetrouwe basis (uit de MCP) + LLM-cognitieve velden. mcp_verwijzingen
    is een interne hulpvariabele en hoort niet in de opgeslagen bron."""
    basis_schoon = {k: v for k, v in bron_basis.items() if k != "mcp_verwijzingen"}
    bid = bron_basis.get("bron_id", "")
    return {
        **basis_schoon,  # bron_id, label, wet, bwbId, artikel, lid, versiedatum, bronreferentie, pad, leden
        "type": out.get("type", ""),
        "reikwijdte": out.get("reikwijdte", ""),
        "geraadpleegde": out.get("geraadpleegde", ""),
        "markeringen": [{**m, "bron_id": bid} for m in out.get("markeringen", [])],
        "verwijzingen": [{**v, "bron_id": bid} for v in out.get("verwijzingen", [])],
        "samenhang": out.get("samenhang", ""),
    }


def _merge_act2_werkgebied(context: dict, out: dict) -> dict:
    """Revise act-2: overlay de LLM-cognitieve velden (markeringen/verwijzingen/samenhang) op de
    brongetrouwe per-bron-basis uit `context` (gematcht op bron_id), zodat het LLM de leden-tekst
    niet kan herschrijven."""
    basis_van = {b.get("bron_id"): b for b in (context.get("bronnen") or [])}
    bronnen = []
    for ob in out.get("bronnen", []):
        bid = ob.get("bron_id", "")
        base = basis_van.get(bid, {})
        bronnen.append({
            "bron_id": bid,
            "label": base.get("label", ""),
            "wet": base.get("wet", ""),
            "bwbId": base.get("bwbId", ""),
            "artikel": base.get("artikel", ""),
            "lid": base.get("lid"),
            "versiedatum": base.get("versiedatum", ""),
            "bronreferentie": base.get("bronreferentie", ""),
            "type": ob.get("type", base.get("type", "")),
            "pad": base.get("pad", ""),
            "leden": base.get("leden", []),
            "reikwijdte": ob.get("reikwijdte", base.get("reikwijdte", "")),
            "geraadpleegde": ob.get("geraadpleegde", base.get("geraadpleegde", "")),
            "markeringen": [{**m, "bron_id": bid} for m in ob.get("markeringen", [])],
            "verwijzingen": [{**v, "bron_id": bid} for v in ob.get("verwijzingen", [])],
            "samenhang": ob.get("samenhang", ""),
        })
    return {
        "werkgebied": context.get("werkgebied", {}),
        "analysefocus": context.get("analysefocus", ""),
        "bronnen": bronnen,
    }


def _merge_act3(context: dict, out: dict) -> dict:
    """Werkgebied-breed act-3: gedeelde begrippen/afleidingsregels + een bron-index voor de
    vindplaatsen. `context` is de act-2-aggregaat (vers) of de vorige act-3 (revise)."""
    return {
        "werkgebied": context.get("werkgebied", {}),
        "bronnen": _bron_index(context),
        "begrippen": out.get("begrippen", []),
        "afleidingsregels": out.get("afleidingsregels", []),
        "validatiepunten": out.get("validatiepunten", []),
    }


async def inventariseer_verwijzingen(llm: LLMClient, bron_basis: dict) -> LLMResult:
    """Fase 2a (per bron) — lichte LLM-stap die alleen de verwijzing-inventaris (+ `volgen`)
    oplevert. Geeft de volledige LLMResult terug zodat de orchestrator de tokens bij de act-2-ronde
    optelt en de fetch-lus aanstuurt op `res.data`."""
    system, user, schema, _ = prompts.act2_inventaris_prompt(bron_basis)
    return await llm.complete(system, user, schema)


async def genereer_act2_bron(
    llm: LLMClient,
    bron_basis: dict,
    ronde: int,
    analysefocus: str | None,
    inventaris: dict | None = None,
    opgehaald: dict | None = None,
) -> tuple[dict, dict]:
    """Genereer markeringen/verwijzingen voor ÉÉN bron en merge met de brongetrouwe bron-basis."""
    system, user, schema, phash = prompts.act2_prompt(bron_basis, analysefocus, inventaris, opgehaald)
    res = await llm.complete(system, user, schema)
    return _merge_bron(bron_basis, res.data), _prov("2", ronde, res, phash, bron_basis)


_BEGRIP_ID_RE = re.compile(r"^b(\d+)$")


def _hernummer_nieuwe_begrippen(
    begrippen: list[dict], nieuwe: list[dict], regels: list[dict],
) -> list[dict]:
    """Nummer de 3b-'nieuwe_begrippen' deterministisch door ná het hoogste bestaande b-nummer
    en remap alle referenties (in de regels én in de nieuwe begrippen zelf) van het oude naar
    het nieuwe id. Zo kan een 3b-id nooit botsen met een 3a-id."""
    if not nieuwe:
        return []
    hoogste = 0
    for b in begrippen:
        m = _BEGRIP_ID_RE.match(b.get("id") or "")
        if m:
            hoogste = max(hoogste, int(m.group(1)))
    mapping: dict[str, str] = {}
    hernummerd: list[dict] = []
    for nb in nieuwe:
        hoogste += 1
        nieuw_id = f"b{hoogste}"
        oud = nb.get("id") or ""
        if oud:
            mapping[oud] = nieuw_id
        hernummerd.append({**nb, "id": nieuw_id})

    def _map(ref: str) -> str:
        return mapping.get(ref, ref)

    for nb in hernummerd:
        nb["verwijst_naar_begrippen"] = [_map(x) for x in (nb.get("verwijst_naar_begrippen") or [])]
        nb["relaties"] = [
            {**rel, "doel_begrip": _map(rel["doel_begrip"])} if isinstance(rel, dict) and rel.get("doel_begrip") else rel
            for rel in (nb.get("relaties") or [])
        ]
    for r in regels:
        uitvoer = r.get("uitvoer")
        if isinstance(uitvoer, dict) and uitvoer.get("begrip_id"):
            uitvoer["begrip_id"] = _map(uitvoer["begrip_id"])
        for item in (r.get("invoer") or []) + (r.get("parameters") or []):
            if isinstance(item, dict) and item.get("begrip_id"):
                item["begrip_id"] = _map(item["begrip_id"])
        for vw in (r.get("voorwaarden") or []):
            if isinstance(vw, dict):
                vw["begrip_ids"] = [_map(x) for x in (vw.get("begrip_ids") or [])]
    return hernummerd


async def genereer_act3(
    llm: LLMClient,
    ronde: int,
    context: dict,
    *,
    omschrijving: str = "",
    analysefocus: str | None = None,
    begrippenlijst: list[dict] | None = None,
) -> tuple[dict, dict]:
    """Werkgebied-brede act-3 over alle bronnen van de act-2-aggregaat `context` — twee LLM-stappen
    binnen één ronde: 3a (begrippen) → 3b (regels met begrip-id's + evt. nieuwe_begrippen)."""
    system, user, schema, phash_a = prompts.act3_begrippen_prompt(
        context, omschrijving, analysefocus, begrippenlijst
    )
    res_a = await llm.complete(system, user, schema)
    begrippen = list(res_a.data.get("begrippen") or [])

    system, user, schema, phash_b = prompts.act3_regels_prompt(context, begrippen)
    res_b = await llm.complete(system, user, schema)
    regels = list(res_b.data.get("afleidingsregels") or [])
    begrippen += _hernummer_nieuwe_begrippen(
        begrippen, list(res_b.data.get("nieuwe_begrippen") or []), regels
    )

    out = {
        "begrippen": begrippen,
        "afleidingsregels": regels,
        "validatiepunten": (
            list(res_a.data.get("validatiepunten") or [])
            + list(res_b.data.get("validatiepunten") or [])
        ),
    }
    prov = _prov("3", ronde, res_b, prompts._hash(phash_a, phash_b), _prov_basis(context))
    prov["tokens_in"] += res_a.tokens_in
    prov["tokens_out"] += res_a.tokens_out
    return _merge_act3(context, out), prov


async def herzie(
    llm: LLMClient,
    activiteit: str,
    context: dict,
    ronde: int,
    vorige: dict,
    feedback: dict,
    *,
    omschrijving: str = "",
    analysefocus: str | None = None,
    begrippenlijst: list[dict] | None = None,
) -> tuple[dict, dict]:
    system, user, schema, phash = prompts.revise_prompt(
        activiteit, context, vorige, feedback,
        omschrijving=omschrijving, analysefocus=analysefocus, begrippenlijst=begrippenlijst,
    )
    res = await llm.complete(system, user, schema)
    if activiteit == "2":
        return _merge_act2_werkgebied(context, res.data), _prov("2", ronde, res, phash, _prov_basis(context))
    # Act-3-revise: `context` is de goedgekeurde act-2-aggregaat — dat levert de bron-index
    # (met versiedatum/bronreferentie) en het werkgebied voor de merge.
    return _merge_act3(context, res.data), _prov("3", ronde, res, phash, _prov_basis(context))
