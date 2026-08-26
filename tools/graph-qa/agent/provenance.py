"""
Bron-provenance uit de tool-executietrace.

Kern van de juridische betrouwbaarheid: bronnen komen uit wat de graaf
daadwerkelijk terugstuurde, NIET uit de prozatekst van het model. Zo passeert een
gehallucineerde citatie niet als "bron", en gaat een echte vindplaats niet verloren
als het model de IRI parafraseert zonder hem uit te typen.

De citatie-herkenning (`iter_refs`) wordt gedeeld met `agent/grounding.py`, dat
dezelfde patronen op de antwoordtekst toepast om niet-onderbouwde verwijzingen te
markeren. We herkennen:
  - document-IRI's in de eigen graafruimte  (zie `agent/namespace.py`)
  - jci-vindplaatsstrings                    (jci1.3:c:BWBR....)
  - kale BWB-id's                            (BWBR\\d+), alleen als losse bron
De vocabulaire-namespace (`ONTOLOGIE`) valt er bewust buiten:
dat zijn predicaten, geen vindplaatsen.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Iterator

from .models import Source
from .namespace import vindplaats_patroon

# Backslash uitgesloten uit de char-class zodat een naijlende escape (bv. "...g=2026-07-01\\")
# niet mee in de IRI/jci wordt gezogen.
_IRI_RE = re.compile(vindplaats_patroon())
_JCI_RE = re.compile(r"jci[\d.]+:c:BWBR\d+[^\s\"'<>)\]}\\]*")
_BWB_RE = re.compile(r"\bBWBR\d+\b")


def _clean(uri: str) -> str:
    return uri.rstrip(".,;\\")


def first_bwb(text: str) -> str | None:
    """Eerste BWB-id in een tekst/citatie, of None."""
    m = _BWB_RE.search(text)
    return m.group(0) if m else None


def iter_refs(text: str) -> Iterator[tuple[str, str | None, str | None]]:
    """Yield (uri, iri, jci) voor elke vindplaats-verwijzing in de tekst (ontdubbeld).

    Een kale BWB-id levert alleen een verwijzing op als hij niet al binnen een
    gevonden IRI/jci valt.
    """
    seen: set[str] = set()

    def emit(uri: str, *, iri: str | None = None, jci: str | None = None):
        uri = _clean(uri)
        if uri and uri not in seen:
            seen.add(uri)
            return (uri, iri, jci)
        return None

    for m in _IRI_RE.finditer(text):
        r = emit(m.group(0), iri=_clean(m.group(0)))
        if r:
            yield r
    for m in _JCI_RE.finditer(text):
        r = emit(m.group(0), jci=_clean(m.group(0)))
        if r:
            yield r
    for m in _BWB_RE.finditer(text):
        bwb = m.group(0)
        if any(bwb in u for u in seen):
            continue
        r = emit(bwb)
        if r:
            yield r


def citations_in(text: str) -> list[str]:
    """Platte lijst van vindplaats-verwijzingen in de tekst (voor grounding)."""
    return [uri for uri, _, _ in iter_refs(text)]


def collect_sources(entries: Iterable[tuple[str, str]]) -> list[Source]:
    """Bouw een ontdubbelde bronnenlijst uit (tool_naam, resultaat_tekst)-paren."""
    sources: list[Source] = []
    seen: set[str] = set()

    for tool, text in entries:
        if not text:
            continue
        for uri, iri, jci in iter_refs(text):
            if uri in seen:
                continue
            seen.add(uri)
            sources.append(Source(label=uri, uri=uri, iri=iri, jci=jci, origin_tool=tool))

    return sources
