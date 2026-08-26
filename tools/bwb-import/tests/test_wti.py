"""Tests voor de WTI-parser en de WTI-verrijking in de writer."""

from __future__ import annotations

from pathlib import Path

from rdflib import RDF, Literal

from app.graphdb_writer import DCTERMS, SKOS, GraphDbWriter
from app.parser import ToestandParser
from app.rdf_vocab import Vocab
from app.wti_parser import WtiParser

FIXTURES = Path(__file__).parent / "fixtures"
V = Vocab()


def _wti():
    return WtiParser().parse(FIXTURES / "sample_wti.xml")


def test_wti_parser_velden() -> None:
    info = _wti()
    assert info.citeertitels == ["Invorderingswet 1990"]
    assert info.afkortingen == ["IW", "IW 1990"]
    assert info.niet_officiele_titels == ["Invorderingswet"]
    assert info.eerstverantwoordelijke == "Financiën"
    assert info.rechtsgebieden == [("Belastingrecht", "Invordering"), ("Bestuursrecht", None)]
    assert info.overheidsdomeinen == ["Belastingen"]
    assert info.grondslagen == ["BWBR0002320"]


def test_wti_parser_authority_wetsfamilie_elementen() -> None:
    info = _wti()
    # OWMS-kern authority (namespace-agnostisch).
    assert info.authority == "Financiën"
    # Wetsfamilie zonder de wet zelf.
    assert info.wetsfamilie == ["BWBR0005537"]
    # Per-regelingelement relaties (grondslag-voor via <gerelateerde-regeling>,
    # verwijzing-door via <gerelateerd-regelingelement>).
    rel = info.element_relaties["2910574"]
    assert rel.grondslag_voor == ["BWBR0047713"]
    assert rel.verwijzing_door == ["BWBR0002126"]
    assert rel.bevoegdheid_voor == []


def test_wti_verrijking_in_graaf() -> None:
    wet = ToestandParser().parse(FIXTURES / "sample_toestand.xml")
    writer = GraphDbWriter(url="http://graphdb:7200", repository="inning", vocab=V)
    g, _ = writer.build_graph(wet, wti=_wti())
    wet_iri = V.wet("BWBR0004770")

    assert (wet_iri, V.ns.afkorting, Literal("IW")) in g
    assert (wet_iri, V.ns.alternatieveTitel, Literal("Invorderingswet", lang="nl")) in g
    assert (wet_iri, V.ns.eerstverantwoordelijke, Literal("Financiën")) in g

    # Rechtsgebieden als skos:Concepten met hiërarchie; wet -> dcterms:subject.
    hoofd = V.begrip("Belastingrecht")
    specifiek = V.begrip("Invordering")
    assert (hoofd, RDF.type, SKOS.Concept) in g
    assert (hoofd, SKOS.prefLabel, Literal("Belastingrecht", lang="nl")) in g
    assert (specifiek, SKOS.broader, hoofd) in g
    assert (wet_iri, DCTERMS.subject, hoofd) in g
    assert (wet_iri, DCTERMS.subject, specifiek) in g
    assert (wet_iri, DCTERMS.subject, V.begrip("Belastingen")) in g

    # Grondslag als edge naar de wet-IRI van de doelregeling (open-world).
    assert (wet_iri, V.ns.heeftGrondslag, V.wet("BWBR0002320")) in g

    # Verantwoordelijke organisatie als wet-overstijgende node + UITGEGEVEN_DOOR.
    org = V.entiteit("organisatie", "Financiën")
    assert (org, RDF.type, V.ns.Organisatie) in g
    assert (wet_iri, V.ns.uitgegevenDoor, org) in g
    # Wetsfamilie-relatie.
    assert (wet_iri, V.ns.inFamilie, V.wet("BWBR0005537")) in g

    # Per-regelingelement relaties koppelen via label-id aan artikel 2.
    art2 = V.by_ref_key("BWBR0004770#artikel=2")
    assert (art2, V.ns.grondslagVoor, V.wet("BWBR0047713")) in g
    assert (art2, V.ns.verwijzingDoor, V.wet("BWBR0002126")) in g


def test_zonder_wti_geen_verrijking() -> None:
    wet = ToestandParser().parse(FIXTURES / "sample_toestand.xml")
    writer = GraphDbWriter(url="http://graphdb:7200", repository="inning", vocab=V)
    g, _ = writer.build_graph(wet)
    assert (None, V.ns.heeftGrondslag, None) not in g
    assert (None, RDF.type, SKOS.Concept) not in g


def test_begrip_iri_slug() -> None:
    assert str(V.begrip("Belastingrecht")) == "urn:bwb:begrip:belastingrecht"
    assert str(V.begrip("Sociale zekerheid & pensioen")) == "urn:bwb:begrip:sociale-zekerheid-pensioen"
