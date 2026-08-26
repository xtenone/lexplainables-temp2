"""WP-C: bronnen komen uit de tool-trace, niet uit prozatekst."""
from __future__ import annotations

from agent.provenance import collect_sources

ART_IRI = "urn:bwb:BWBR0004770:artikel:9"
JCI = "jci1.3:c:BWBR0004770&artikel=9&lid=1"


def test_iri_uit_toolresultaat_wordt_bron():
    sources = collect_sources([("graphdb_sparql", f"resultaat: <{ART_IRI}> bwb:nummer 9")])
    uris = [s.uri for s in sources]
    assert ART_IRI in uris
    src = next(s for s in sources if s.uri == ART_IRI)
    assert src.iri == ART_IRI
    assert src.origin_tool == "graphdb_sparql"


def test_jci_vindplaats_wordt_bron():
    sources = collect_sources([("graphdb_sparql", f'"{JCI}"')])
    src = next(s for s in sources if s.uri == JCI)
    assert src.jci == JCI


def test_prozatekst_is_geen_bron():
    # collect_sources krijgt de modeltekst nooit; een gehallucineerde citatie
    # in het eindantwoord kan dus per definitie niet als bron opduiken.
    sources = collect_sources([])
    assert sources == []


def test_vocabulaire_namespace_telt_niet_mee():
    # urn:bwb-ns:... zijn predicaten, geen vindplaatsen.
    sources = collect_sources([("t", "?s <urn:bwb-ns:heeftLid> ?o")])
    assert sources == []


def test_kale_bwb_niet_dubbel_als_al_in_iri():
    sources = collect_sources([("t", f"{ART_IRI} hoort bij BWBR0004770")])
    uris = [s.uri for s in sources]
    assert uris == [ART_IRI]  # geen losse BWBR0004770 erbij


def test_dedup_over_meerdere_rondes():
    sources = collect_sources([("t1", ART_IRI), ("t2", ART_IRI)])
    assert len([s for s in sources if s.uri == ART_IRI]) == 1
