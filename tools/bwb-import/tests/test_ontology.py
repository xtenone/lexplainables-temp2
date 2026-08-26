"""Tests voor de T-Box: ELI-alignment, volledigheid t.o.v. de writer-output.

De driftbescherming bouwt een echte wet-graaf en controleert dat elke
``bwb:``-term die daarin voorkomt ook in de ontologie is gedeclareerd —
zo kan de writer geen termen introduceren zonder schema.
"""

from __future__ import annotations

from pathlib import Path

from rdflib import OWL, RDF, RDFS, URIRef

from app.graphdb_writer import GraphDbWriter
from app.ontology import ELI, build_ontology, gedeclareerde_termen
from app.parser import ToestandParser
from app.rdf_vocab import Vocab

FIXTURES = Path(__file__).parent / "fixtures"
V = Vocab()


def test_ontologie_declareert_owl_ontology() -> None:
    g = build_ontology(V)
    assert (V.ontology_resource, RDF.type, OWL.Ontology) in g


def test_eli_alignment() -> None:
    g = build_ontology(V)
    assert (V.klasse("Regeling"), RDFS.subClassOf, ELI.LegalResource) in g
    assert (V.klasse("Citeerbaar"), RDFS.subClassOf, ELI.LegalResource) in g
    assert (V.klasse("Artikel"), RDFS.subClassOf, ELI.LegalResourceSubdivision) in g
    assert (V.klasse("Hoofdstuk"), RDFS.subClassOf, V.klasse("Structuurdeel")) in g
    assert (V.ns.heeftArtikel, RDFS.subPropertyOf, ELI.has_part) in g
    assert (V.ns.verwijstNaar, RDFS.subPropertyOf, ELI.cites) in g
    assert (V.ns.citeertitel, RDFS.subPropertyOf, ELI.title) in g
    assert (V.ns.geldigVanaf, RDFS.subPropertyOf, ELI.first_date_entry_in_force) in g


def test_regeling_subklassen_per_soort() -> None:
    g = build_ontology(V)
    subklassen = (
        "Wet",
        "AMvB",
        "KoninklijkBesluit",
        "MinisterieleRegeling",
        "Beleidsregel",
        "Circulaire",
    )
    for naam in subklassen:
        assert (V.klasse(naam), RDFS.subClassOf, V.klasse("Regeling")) in g, naam
    assert (V.ns.heeftGrondslag, RDFS.range, V.klasse("Regeling")) in g


def test_elke_klasse_en_property_heeft_label_en_comment() -> None:
    g = build_ontology(V)
    for term in gedeclareerde_termen(V):
        labels = [o for o in g.objects(term, RDFS.label)]
        comments = [o for o in g.objects(term, RDFS.comment)]
        assert labels and labels[0].language == "nl", term
        assert comments and comments[0].language == "nl", term


def _gebruikte_bwb_termen(bestand: str) -> set[URIRef]:
    """Alle bwb-termen (klassen + predicaten) in een gebouwde wet-graaf."""
    wet = ToestandParser().parse(FIXTURES / bestand)
    writer = GraphDbWriter(url="http://graphdb:7200", repository="inning", vocab=V)
    g, _ = writer.build_graph(wet)
    ns = str(V.ns)
    termen: set[URIRef] = set()
    for _s, p, o in g:
        if str(p).startswith(ns):
            termen.add(p)
        if p == RDF.type and str(o).startswith(ns):
            termen.add(o)  # type: ignore[arg-type]
    return termen


def test_writer_gebruikt_alleen_gedeclareerde_termen() -> None:
    gedeclareerd = gedeclareerde_termen(V)
    for bestand in ("sample_toestand.xml", "sample_circulaire.xml", "sample_regeling.xml"):
        ontbrekend = _gebruikte_bwb_termen(bestand) - gedeclareerd
        assert not ontbrekend, f"{bestand}: termen zonder T-Box-declaratie: {ontbrekend}"


def test_sameas_naar_wettenoverheid() -> None:
    wet = ToestandParser().parse(FIXTURES / "sample_toestand.xml")
    writer = GraphDbWriter(url="http://graphdb:7200", repository="inning", vocab=V)
    g, _ = writer.build_graph(wet)
    assert (
        V.wet("BWBR0004770"),
        OWL.sameAs,
        URIRef("https://wetten.overheid.nl/BWBR0004770"),
    ) in g
    # Artikel -> jci-resolver-URL.
    art1 = V.by_ref_key("BWBR0004770#artikel=1")
    assert (
        art1,
        OWL.sameAs,
        URIRef("https://wetten.overheid.nl/jci1.3:c:BWBR0004770&artikel=1"),
    ) in g
    # Toestand-identiteit als eigen property (geen sameAs: ander FRBR-niveau).
    assert (
        V.wet("BWBR0004770"),
        V.ns.toestandUrl,
        URIRef("http://wetten.overheid.nl/id/BWBR0004770/2026-01-01/0"),
    ) in g


def test_ontologie_graph_iri() -> None:
    assert str(V.ontology_graph()) == "urn:bwb:graph:ontologie"
