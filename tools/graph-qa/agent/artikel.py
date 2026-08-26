"""Gestructureerde artikeltekst uit de graaf.

Eén bron voor zowel de **weergave** (documentpaneel in de workbench) als de **annotatie-corpus**: beide
komen uit `queries.get_artikel` op GraphDB, geparseerd via `parse_select`. Zo is er geen drift tussen
wat de jurist ziet en waartegen de brongetrouwheid van de agent wordt gecheckt.
"""
from __future__ import annotations

import logging
import re

from .graph import queries
from .graph.results import parse_select
from .ports import GraphPort

logger = logging.getLogger("graph_qa.artikel")


class OngeldigeVindplaats(ValueError):
    """De aanduiding kan geen bepaling zijn — een tikfout, geen lege graaf.

    Dit onderscheid bestond niet: één `except ValueError` dekte twee gevallen (de decimale-nummer-
    fallback, die bedoeld is, en echte invoerfouten, die dat niet zijn), waarna het endpoint 200 met
    een lege tekst gaf. De jurist zag dan een leeg documentpaneel zonder uitleg en kon niet zien of
    hij zich vertypte, of de graaf de bepaling niet kent, of de dienst stuk was.
    """

_NUM = re.compile(r"\d+")


def _lidsleutel(lid: str) -> tuple[int, str]:
    """Numeriek sorteren op lidnummer (de SPARQL ORDER BY ?lid is lexicaal: 1,10,11,2,…)."""
    m = _NUM.search(lid or "")
    return (int(m.group()) if m else 10**9, lid or "")


def _match_lid(lidnummer: str, lid: str) -> bool:
    """Vergelijk lidnummers robuust ('1' == '01'); valt terug op string-gelijkheid."""
    a, b = _lidsleutel(lidnummer), _lidsleutel(lid)
    if a[0] != 10**9 and b[0] != 10**9:
        return a[0] == b[0]
    return (lidnummer or "").strip() == (lid or "").strip()


def _bepaling_fallback(bwb_id: str, artikel: str, graph: GraphPort) -> list[dict]:
    """Beleidsregels/circulaires (decimale nummers zoals '9.1') gaan niet via het artikel/lid-IRI-
    patroon; haal ze dan op via `bwb:nummer` (get_bepaling)."""
    try:
        rows = parse_select(graph.sparql(queries.get_bepaling(bwb_id, artikel)))
    except ValueError:
        return []
    tekst = next((r.get("tekst") for r in rows if (r.get("tekst") or "").strip()), "")
    return [{"lid": "", "tekst": tekst.strip()}] if tekst.strip() else []


def _controleer_vindplaats(bwb_id: str, artikel: str, lid: str | None) -> None:
    """Kan dit überhaupt een bepaling aanduiden? Zo nee: een tikfout, en dat is iets anders dan niets
    gevonden. De query-bouwers valideren streng; hier vragen we ze dat alvast, vóór er een SPARQL de
    deur uit gaat."""
    try:
        queries.regeling_iri(bwb_id)
    except ValueError as exc:
        raise OngeldigeVindplaats(str(exc)) from exc
    # Een artikelnummer ('9', '22a') óf een bepaling-nummer ('9.1'): één van de twee moet passen.
    for bouwer in (queries._art, queries._nummer_vrij):
        try:
            bouwer(artikel)
            break
        except ValueError:
            continue
    else:
        raise OngeldigeVindplaats(f"Ongeldige aanduiding: {artikel!r} (verwacht bv. '9', '22a' of '9.1').")
    if lid and str(lid).strip():
        try:
            queries._num(str(lid))
        except ValueError as exc:
            raise OngeldigeVindplaats(str(exc)) from exc


def _leden_en_corpus(bwb_id: str, artikel: str, graph: GraphPort, lid: str | None = None) -> tuple[list[dict], str]:
    """(leden_teksten, corpus) uit de graaf. Corpus = de leden samengevoegd ('N. tekst'),
    of de artikeltekst zelf als er geen genummerde leden zijn. Met `lid` scope je tot dat ene lid.
    Voor decimale/divisie-nummers valt het terug op get_bepaling (bv. Leidraad '9.1')."""
    _controleer_vindplaats(bwb_id, artikel, lid)
    try:
        rows = parse_select(graph.sparql(queries.get_artikel(bwb_id, artikel)))
    except ValueError:
        rows = []  # bv. artikel "9.1" wordt door get_artikel geweigerd → straks de bepaling-fallback
    art_tekst = next((r["tekst"] for r in rows if r.get("tekst")), "")
    leden: list[dict] = []
    for r in rows:
        tekst = (r.get("lidtekst") or "").strip()
        if tekst:
            leden.append({"lid": (r.get("lidnummer") or "").strip(), "tekst": tekst})
    leden.sort(key=lambda ld: _lidsleutel(ld["lid"]))
    lid_gevraagd = bool(lid and str(lid).strip())
    if lid_gevraagd:
        leden = [ld for ld in leden if _match_lid(ld["lid"], str(lid))]
    elif not leden and art_tekst.strip():
        leden = [{"lid": "", "tekst": art_tekst.strip()}]
    # Bepaling-fallback (decimaal nummer zoals '9.1') alleen zónder specifiek lid; een niet-bestaand
    # lid levert leeg op i.p.v. terug te vallen op de hele bepaling.
    if not leden and not lid_gevraagd:
        leden = _bepaling_fallback(bwb_id, artikel, graph)
    corpus = "\n\n".join((f'{ld["lid"]}. {ld["tekst"]}' if ld["lid"] else ld["tekst"]) for ld in leden)
    return leden, corpus


def artikel_corpus(bwb_id: str, artikel: str, graph: GraphPort, lid: str | None = None) -> str:
    """Alleen de corpus-tekst (voor de annotatie-flow; één SPARQL, geen regeling-info)."""
    return _leden_en_corpus(bwb_id, artikel, graph, lid)[1]


def haal_artikel_sync(bwb_id: str, artikel: str, graph: GraphPort, lid: str | None = None) -> dict:
    """Volledige artikelinfo voor de workbench-weergave: leden-teksten + citeertitel + corpus.
    Met `lid` beperk je de weergave tot dat ene lid."""
    leden, corpus = _leden_en_corpus(bwb_id, artikel, graph, lid)
    citeertitel = ""
    try:
        info = parse_select(graph.sparql(queries.get_regeling_info(bwb_id)))
        if info:
            citeertitel = (info[0].get("citeertitel") or "").strip()
    except Exception:  # citeertitel is cosmetisch — nooit de artikeltekst blokkeren
        logger.warning("citeertitel ophalen mislukt", exc_info=True)
    return {
        "bwbId": bwb_id,
        "artikel": artikel,
        "citeertitel": citeertitel,
        "opschrift": "",
        "leden_teksten": leden,
        "corpus": corpus,
    }
