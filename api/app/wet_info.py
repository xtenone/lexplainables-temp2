"""Wetsstructuur- en artikelinfo voor de UI (autocomplete + lid-keuze).

Dunne service over `WettenbankClient`: plat de geneste MCP-structuurboom af naar één
artikellijst-met-pad voor de artikel-combobox, en vat een artikel samen (leden + opschrift +
tekstsnippet) voor de lid-keuzelijst. Beide met een in-proces TTL-cache (vgl. `app_settings`):
de data wijzigt hoogstens bij een nieuwe wetsversie, en de MCP cachet de onderliggende XML
zelf ook een uur — dit bespaart vooral de MCP-roundtrip per formulier-interactie.
Fouten worden bewust niet gecachet (een tijdelijke MCP-storing mag geen uur blijven hangen).
"""

from __future__ import annotations

import time

from .wettenbank import WettenbankClient

_TTL_S = 3600.0
_STRUCTUUR_CAP = 64
_ARTIKEL_CAP = 512
_SNIPPET_LEN = 200

# (waarde, vervaltijd) per sleutel; dicts zijn insertion-ordered → oudste-eerst-evictie.
_structuur_cache: dict[str, tuple[dict, float]] = {}
_artikel_cache: dict[tuple[str, str], tuple[dict, float]] = {}


def _nu() -> float:
    return time.monotonic()


def _wis_cache() -> None:
    """Voor tests: begin met lege caches."""
    _structuur_cache.clear()
    _artikel_cache.clear()


def _uit_cache(cache: dict, key):
    treffer = cache.get(key)
    if treffer is not None and treffer[1] > _nu():
        return treffer[0]
    return None


def _in_cache(cache: dict, key, waarde, cap: int) -> None:
    cache.pop(key, None)
    while len(cache) >= cap:
        cache.pop(next(iter(cache)))
    cache[key] = (waarde, _nu() + _TTL_S)


# --- structuur afplatten ---------------------------------------------------------

def _label(node: dict) -> str:
    """Leesbaar label voor een structuurcontainer: de titel, anders '{Type} {nr}'."""
    titel = (node.get("titel") or "").strip()
    if titel:
        return titel
    stuk = f"{str(node.get('type') or '').capitalize()} {node.get('nr') or ''}".strip()
    # De platte fallback-node ({type:"wet", nr:""}) levert geen zinvol pad-segment.
    return "" if stuk.lower() == "wet" else stuk


def _plat(structuur: list[dict]) -> list[dict]:
    """Plat de geneste structuurboom af naar [{artikel, pad}] in documentvolgorde."""
    resultaat: list[dict] = []

    def loop(nodes: list[dict], pad: list[str]) -> None:
        for node in nodes:
            label = _label(node)
            hier = [*pad, label] if label else pad
            for nr in node.get("artikelen") or []:
                resultaat.append({"artikel": nr, "pad": " › ".join(hier)})
            loop(node.get("secties") or [], hier)

    loop(structuur, [])
    return resultaat


async def structuur_overzicht(client: WettenbankClient, bwb_id: str) -> dict:
    """Afgeplatte artikellijst van een wet: {bwbId, citeertitel, versiedatum, artikelen[]}."""
    cached = _uit_cache(_structuur_cache, bwb_id)
    if cached is not None:
        return cached
    data = await client.structuur(bwb_id)
    overzicht = {
        "bwbId": data.get("bwbId") or bwb_id,
        "citeertitel": data.get("citeertitel") or "",
        "versiedatum": data.get("versiedatum") or "",
        "artikelen": _plat(data.get("structuur") or []),
    }
    _in_cache(_structuur_cache, bwb_id, overzicht, _STRUCTUUR_CAP)
    return overzicht


# --- artikelinfo -----------------------------------------------------------------

def _snippet(tekst: str, limiet: int = _SNIPPET_LEN) -> str:
    """Eerste ±`limiet` tekens, afgekapt op een woordgrens."""
    tekst = " ".join(tekst.split())
    if len(tekst) <= limiet:
        return tekst
    kop = tekst[:limiet]
    spatie = kop.rfind(" ")
    if spatie > limiet // 2:
        kop = kop[:spatie]
    return kop + "…"


async def artikel_info(client: WettenbankClient, bwb_id: str, artikel: str) -> dict:
    """Samenvatting van één artikel voor de lid-keuze: leden + opschrift + snippet."""
    key = (bwb_id, artikel)
    cached = _uit_cache(_artikel_cache, key)
    if cached is not None:
        return cached
    data = await client.artikel(bwb_id, artikel)
    leden = [
        str(lid.get("lid"))
        for lid in data.get("leden") or []
        if str(lid.get("lid") or "").strip()  # ongenummerd lid (leeg nr) is geen keuze
    ]
    eerste_tekst = next((lid.get("tekst") or "" for lid in data.get("leden") or []), "")
    info = {
        "bwbId": data.get("bwbId") or bwb_id,
        "artikel": data.get("artikel") or artikel,
        "citeertitel": data.get("citeertitel") or "",
        "opschrift": data.get("sectie") or "",
        "pad": data.get("pad") or "",
        "leden": leden,
        "leden_teksten": [
            {"lid": str(lid.get("lid") or ""), "tekst": lid.get("tekst") or ""}
            for lid in data.get("leden") or []
        ],
        "snippet": _snippet(eerste_tekst),
    }
    _in_cache(_artikel_cache, key, info, _ARTIKEL_CAP)
    return info
