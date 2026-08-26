"""Tests voor de GraphDB-writer: bouw de RDF-graaf en assert triples (geen HTTP).

``build_graph`` is puur offline; alleen ``ensure_constraints``/``write_wet`` doen
netwerk-I/O. We controleren klassen, het ref_key-afgeleide IRI-schema, de
structuur-/volg-/verwijs-relaties en dat een cross-referentie exact op de
doel-artikel-IRI uitkomt (open-world, geen stubs).
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from rdflib import RDF, RDFS, XSD, Literal

from app.graphdb_writer import GraphDbWriter, _fts_connector_config
from app.models import (
    Artikel,
    Divisie,
    Lid,
    Onderdeel,
    Structuurdeel,
    Verwijzing,
    VerwijzingSoort,
    Wet,
)
from app.parser import ToestandParser
from app.rdf_vocab import Vocab

FIXTURES = Path(__file__).parent / "fixtures"
V = Vocab()


def _echte_wet() -> Wet:
    return ToestandParser().parse(FIXTURES / "sample_toestand.xml")


def _writer() -> GraphDbWriter:
    return GraphDbWriter(url="http://graphdb:7200", repository="inning", vocab=V)


def _kleine_wet() -> Wet:
    lid1 = Lid(id="W#a1#l1", nummer="1", tekst="tekst", verwijzingen=[])
    lid2 = Lid(
        id="W#a1#l2",
        nummer="2",
        tekst="zie awb",
        verwijzingen=[
            Verwijzing(
                soort=VerwijzingSoort.EXTERN,
                tekst="artikel 3:40",
                doel_bwb_id="BWBR0005537",
                doc="jci1.3:c:BWBR0005537&artikel=3:40",
            )
        ],
    )
    art1 = Artikel(
        id="W#a1",
        nummer="1",
        label="Artikel 1",
        tekst="",
        jci="jci1.3:c:BWBR0000001&artikel=1",
        leden=[lid1, lid2],
    )
    art2 = Artikel(
        id="W#a2",
        nummer="2",
        label="Artikel 2",
        tekst="x",
        jci="jci1.3:c:BWBR0000001&artikel=2",
        inwerking="2016-05-01",
        bron="Stb.2016-163",
        onderdelen=[
            Onderdeel(
                id="W#a2#o-a",
                nummer="a.",
                tekst="definitie met verwijzing",
                verwijzingen=[
                    Verwijzing(
                        soort=VerwijzingSoort.EXTERN,
                        tekst="artikel 1 Awr",
                        doel_bwb_id="BWBR0002320",
                        doc="jci1.3:c:BWBR0002320&artikel=1",
                    )
                ],
            )
        ],
    )
    hoofdstuk = Structuurdeel(
        id="W#hI",
        soort="hoofdstuk",
        nummer="I",
        label="Hoofdstuk",
        titel="Algemeen",
        artikelen=[art1, art2],
    )
    return Wet(
        bwb_id="BWBR0000001",
        citeertitel="Testwet",
        opschrift="Wet test",
        soort="wet",
        structuurdelen=[hoofdstuk],
    )


def _kleine_circulaire() -> Wet:
    sub = Divisie(
        id="C#d1#d1.1",
        nummer="1.1",
        label="Artikel 1.1",
        titel="Nader",
        tekst="subtekst",
        jci="jci1.3:c:BWBR0099999&artikel=1.1",
        verwijzingen=[
            Verwijzing(
                soort=VerwijzingSoort.EXTERN,
                tekst="artikel 19",
                doel_bwb_id="BWBR0004770",
                doc="jci1.3:c:BWBR0004770&artikel=19",
            )
        ],
    )
    top = Divisie(
        id="C#d1",
        nummer="1",
        label="Artikel 1",
        titel="Inleiding",
        tekst="hoofdtekst",
        jci="jci1.3:c:BWBR0099999&artikel=1",
        verwijzingen=[
            Verwijzing(
                soort=VerwijzingSoort.EXTERN,
                tekst="artikel 4",
                doel_bwb_id="BWBR0004770",
                doc="jci1.3:c:BWBR0004770&artikel=4",
            )
        ],
        subdivisies=[sub],
    )
    return Wet(
        bwb_id="BWBR0099999",
        citeertitel="Testleidraad",
        opschrift="Test-circulaire",
        soort="circulaire",
        divisies=[top],
    )


def test_telling_klopt() -> None:
    _, summary = _writer().build_graph(_kleine_wet())
    assert summary.wetten == 1
    assert summary.hoofdstukken == 1
    assert summary.artikelen == 2
    assert summary.leden == 2
    assert summary.onderdelen == 1
    assert summary.relaties > 0


def test_klassen_en_ref_key_iri() -> None:
    g, _ = _writer().build_graph(_kleine_wet())
    wet = V.wet("BWBR0000001")
    art1 = V.by_ref_key("BWBR0000001#artikel=1")
    # Hoofdstuk zonder jci maar mét nummer: ref_key-afgeleide IRI (citeerbaar).
    hoofdstuk = V.by_ref_key("BWBR0000001#hoofdstuk=I")

    # De wet draagt het generieke Regeling-type, de soort-subklasse én Citeerbaar.
    assert (wet, RDF.type, V.klasse("Regeling")) in g
    assert (wet, RDF.type, V.klasse("Wet")) in g
    assert (wet, RDF.type, V.klasse("Citeerbaar")) in g
    # Artikel draagt zowel de eigen klasse als het gedeelde Citeerbaar-type.
    assert (art1, RDF.type, V.klasse("Artikel")) in g
    assert (art1, RDF.type, V.klasse("Citeerbaar")) in g
    assert (hoofdstuk, RDF.type, V.klasse("Citeerbaar")) in g
    # Structuur- en volgrelaties.
    assert (wet, V.ns.heeftHoofdstuk, hoofdstuk) in g
    assert (hoofdstuk, V.ns.heeftArtikel, art1) in g
    art2 = V.by_ref_key("BWBR0000001#artikel=2")
    assert (art2, V.ns.volgtOp, art1) in g
    # Literals: nummer + refKey op het artikel.
    assert (art1, V.ns.nummer, Literal("1")) in g
    assert (art1, V.ns.refKey, Literal("BWBR0000001#artikel=1")) in g
    # Skip-props: geen id/stub als literal.
    assert (art1, V.ns.id, Literal("W#a1")) not in g


def test_rdfs_labels() -> None:
    g, _ = _writer().build_graph(_kleine_wet())
    # Wet -> citeertitel; Artikel -> label-prop. Labels dragen @nl.
    assert (V.wet("BWBR0000001"), RDFS.label, Literal("Testwet", lang="nl")) in g
    art1 = V.by_ref_key("BWBR0000001#artikel=1")
    assert (art1, RDFS.label, Literal("Artikel 1", lang="nl")) in g
    # Extern verwijs-doel krijgt een leesbaar fallback-label.
    doel = V.by_ref_key("BWBR0005537#artikel=3:40")
    assert (doel, RDFS.label, Literal("art. 3:40 (BWBR0005537)", lang="nl")) in g


def test_datums_zijn_xsd_date() -> None:
    g, _ = _writer().build_graph(_kleine_wet())
    art2 = V.by_ref_key("BWBR0000001#artikel=2")
    assert (art2, V.ns.inwerking, Literal("2016-05-01", datatype=XSD.date)) in g


def test_tekst_heeft_nl_tag() -> None:
    g, _ = _writer().build_graph(_kleine_wet())
    art2 = V.by_ref_key("BWBR0000001#artikel=2")
    assert (art2, V.ns.tekst, Literal("x", lang="nl")) in g
    assert (V.wet("BWBR0000001"), V.ns.citeertitel, Literal("Testwet", lang="nl")) in g


def test_ongeldige_datum_valt_terug_op_string() -> None:
    assert Vocab.literal("inwerking", "onbekend") == Literal("onbekend")
    assert Vocab.literal("publicatienr", "163a") == Literal("163a")
    assert Vocab.literal("publicatiejaar", "1990") == Literal("1990", datatype=XSD.gYear)
    assert Vocab.literal("publicatienr", "163") == Literal("163", datatype=XSD.integer)


def test_verwijzing_wijst_naar_doel_artikel_iri() -> None:
    g, _ = _writer().build_graph(_kleine_wet())
    art1 = V.by_ref_key("BWBR0000001#artikel=1")
    doel = V.by_ref_key("BWBR0005537#artikel=3:40")  # uit lid 2 van artikel 1
    # Directe edge + tussenresource met soort/doc.
    assert (art1, V.ns.verwijstNaar, doel) in g
    vw = V.verwijzing(art1, doel, "extref")
    assert (art1, V.ns.heeftVerwijzing, vw) in g
    assert (vw, RDF.type, V.klasse("Verwijzing")) in g
    assert (vw, V.ns.naar, doel) in g
    assert (vw, V.ns.soort, Literal("extref")) in g
    assert (vw, V.ns.doc, Literal("jci1.3:c:BWBR0005537&artikel=3:40")) in g


def test_circulaire_divisies_en_cross_ref() -> None:
    g, summary = _writer().build_graph(_kleine_circulaire())
    assert summary.divisies == 2
    assert summary.artikelen == 0

    top = V.by_ref_key("BWBR0099999#artikel=1")
    sub = V.by_ref_key("BWBR0099999#artikel=1.1")
    assert (top, RDF.type, V.klasse("Divisie")) in g
    assert (top, RDF.type, V.klasse("Citeerbaar")) in g
    assert (top, V.ns.heeftDivisie, sub) in g

    # Cross-refs komen exact op de doelwet-artikel-IRI uit (determinisme).
    assert (top, V.ns.verwijstNaar, V.by_ref_key("BWBR0004770#artikel=4")) in g
    assert (sub, V.ns.verwijstNaar, V.by_ref_key("BWBR0004770#artikel=19")) in g


def _regeling_met_soort(soort: str) -> Wet:
    wet = _kleine_wet()
    return replace(wet, soort=soort)


def test_soort_subklassen() -> None:
    # Elke bekende soort levert de subklasse + het generieke Regeling-type.
    for soort, subklasse in (
        ("wet", "Wet"),
        ("ministeriele-regeling", "MinisterieleRegeling"),
        ("beleidsregel", "Beleidsregel"),
        ("circulaire", "Circulaire"),
        ("AMvB", "AMvB"),
        ("KB", "KoninklijkBesluit"),
    ):
        g, _ = _writer().build_graph(_regeling_met_soort(soort))
        node = V.wet("BWBR0000001")
        assert (node, RDF.type, V.klasse("Regeling")) in g, soort
        assert (node, RDF.type, V.klasse(subklasse)) in g, soort


def test_onbekende_soort_alleen_regeling() -> None:
    g, _ = _writer().build_graph(_regeling_met_soort("verdrag"))
    node = V.wet("BWBR0000001")
    typen = {o for o in g.objects(node, RDF.type)}
    assert typen == {V.klasse("Regeling"), V.klasse("Citeerbaar")}
    # rdfs:label blijft de citeertitel (regressie op de _rdfs_label-branch).
    assert (node, RDFS.label, Literal("Testwet", lang="nl")) in g


def test_hele_structuur_verwijzingen_niet_gedropt() -> None:
    """Verwijzingen naar titeldelen/hoofdstukken/afdelingen/hele wetten blijven."""
    g, _ = _writer().build_graph(_echte_wet())
    lid2 = V.by_ref_key("BWBR0004770#artikel=1#lid=2")
    assert (lid2, V.ns.verwijstNaar, V.by_ref_key("BWBR0005537#titeldeel=4.1")) in g
    assert (lid2, V.ns.verwijstNaar, V.by_ref_key("BWBR0005537#hoofdstuk=6")) in g
    assert (lid2, V.ns.verwijstNaar, V.by_ref_key("BWBR0005537#afdeling=10.2.1")) in g
    # Hele-wet-doel: de wet-IRI zelf.
    assert (None, V.ns.verwijstNaar, V.wet("BWBR0002471")) in g
    # Fallback-label voor het externe structuurdoel.
    doel = V.by_ref_key("BWBR0005537#hoofdstuk=6")
    assert (doel, RDFS.label, Literal("hoofdstuk 6 (BWBR0005537)", lang="nl")) in g


def test_onderdeel_heeft_ref_key_iri() -> None:
    """Onderdelen met een &o=-jci zijn citeerbaar (genest: herhaalde #o=)."""
    g, _ = _writer().build_graph(_echte_wet())
    onderdeel = V.by_ref_key("BWBR0004770#artikel=2#lid=1#o=aa#o=1")
    assert (onderdeel, RDF.type, V.klasse("Onderdeel")) in g
    assert (onderdeel, RDF.type, V.klasse("Citeerbaar")) in g
    # Structuurdeel eveneens citeerbaar op zijn jci.
    hoofdstuk = V.by_ref_key("BWBR0004770#hoofdstuk=I")
    assert (hoofdstuk, RDF.type, V.klasse("Hoofdstuk")) in g
    assert (hoofdstuk, RDF.type, V.klasse("Citeerbaar")) in g


def test_verwijzing_vanaf_onderdeel_blijft_op_onderdeel() -> None:
    """Onderdeel-refs hangen aan het onderdeel zelf, niet meer aan het artikel."""
    g, _ = _writer().build_graph(_echte_wet())
    onderdeel_a = V.by_ref_key("BWBR0004770#artikel=2#lid=1#o=a")
    awr_art1 = V.by_ref_key("BWBR0002320#artikel=1")
    assert (onderdeel_a, V.ns.verwijstNaar, awr_art1) in g
    artikel2 = V.by_ref_key("BWBR0004770#artikel=2")
    assert (artikel2, V.ns.verwijstNaar, awr_art1) not in g


def test_doel_pad_en_ankertekst_op_verwijzing() -> None:
    g, _ = _writer().build_graph(_echte_wet())
    bron = V.by_ref_key("BWBR0004770#artikel=2#lid=1#o=g")
    doel = V.by_ref_key("BWBR0004770#hoofdstuk=VIIa")
    vw = V.verwijzing(bron, doel, "intref")
    assert (vw, V.ns.doelPad, Literal("/HoofdstukVIIa")) in g
    assert (vw, V.ns.doelSoort, Literal("hoofdstuk")) in g
    assert (vw, V.ns.ankerTekst, Literal("hoofdstuk VIIA", lang="nl")) in g
    assert (vw, V.ns.verwijzingId, Literal("2386592")) in g


def test_tekstuele_fallback_verwijzing() -> None:
    """Ongetagde tekstverwijzingen worden gedetecteerd, gemarkeerd 'laag'."""
    g, _ = _writer().build_graph(_echte_wet())
    bron = V.by_ref_key("BWBR0004770#artikel=2#lid=1#o=t")
    doel = V.by_ref_key("BWBR0004770#artikel=112")
    assert (bron, V.ns.verwijstNaar, doel) in g
    vw = V.verwijzing(bron, doel, "tekstueel")
    assert (vw, V.ns.soort, Literal("tekstueel")) in g
    assert (vw, V.ns.betrouwbaarheid, Literal("laag")) in g


def test_tekstuele_fallback_uitschakelbaar() -> None:
    writer = GraphDbWriter(
        url="http://graphdb:7200", repository="inning", vocab=V, tekstuele_refs=False
    )
    g, _ = writer.build_graph(_echte_wet())
    assert (None, V.ns.soort, Literal("tekstueel")) not in g


def test_named_graph_per_wet() -> None:
    # De graaf-IRI hangt aan het bwb-id (idempotente re-import per wet).
    assert str(V.graph("BWBR0000001")) == "urn:bwb:graph:BWBR0000001"


def test_serialiseert_naar_turtle() -> None:
    g, _ = _writer().build_graph(_kleine_wet())
    turtle = g.serialize(format="turtle")
    assert "bwb:" in turtle and "BWBR0000001" in turtle


# ------------------------------------------------------------- FTS-connector
class _StubResponse:
    def __init__(self, payload: dict | None = None) -> None:
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class _StubSession:
    """Minimale requests.Session-vervanger die SPARQL-calls opneemt.

    ``bestaande_config`` bepaalt het antwoord op de listConnectors-SELECT.
    """

    def __init__(self, bestaande_config: dict | None = None, rauw: str | None = None) -> None:
        self.updates: list[str] = []
        self._bestaand = bestaande_config
        # `rauw` bootst de GraphDB-versies na die géén JSON-config teruggeven maar
        # bijvoorbeeld alleen de connectornaam.
        self._rauw = rauw

    def post(self, url: str, *, data=None, **_kw) -> _StubResponse:
        data = data or {}
        if "query" in data:
            bindings = []
            if self._rauw is not None:
                bindings = [{"createString": {"value": self._rauw}}]
            elif self._bestaand is not None:
                bindings = [{"createString": {"value": json.dumps(self._bestaand)}}]
            return _StubResponse({"results": {"bindings": bindings}})
        self.updates.append(data["update"])
        return _StubResponse()


def _fts_writer(session: _StubSession) -> GraphDbWriter:
    return GraphDbWriter(url="http://graphdb:7200", repository="inning", vocab=V, session=session)


def test_fts_config_dekt_tekstvelden_en_typen() -> None:
    config = _fts_connector_config(V)
    assert str(V.klasse("Artikel")) in config["types"]
    assert str(V.klasse("Onderdeel")) in config["types"]
    # Het generieke Regeling-type (elke wet/regeling draagt het) i.p.v. Wet.
    assert str(V.klasse("Regeling")) in config["types"]
    assert str(V.klasse("Wet")) not in config["types"]
    veldnamen = {veld["fieldName"] for veld in config["fields"]}
    assert {"tekst", "titel", "citeertitel", "voetnoot", "definieertBegrip", "label"} <= veldnamen
    assert config["languages"] == ["nl", ""]
    assert config["analyzer"].endswith("DutchAnalyzer")


def test_ensure_fts_maakt_connector_aan_wanneer_afwezig() -> None:
    session = _StubSession(bestaande_config=None)
    _fts_writer(session).ensure_fts_connector()
    assert len(session.updates) == 1
    assert "createConnector" in session.updates[0]
    assert "DutchAnalyzer" in session.updates[0]


def test_ensure_fts_is_idempotent_bij_actuele_config() -> None:
    # GraphDB geeft de config terug aangevuld met defaults; dat mag geen
    # herindexering triggeren.
    bestaand = json.loads(json.dumps(_fts_connector_config(V)))
    bestaand["readonly"] = False
    for veld in bestaand["fields"]:
        veld["indexed"] = True
    session = _StubSession(bestaande_config=bestaand)
    _fts_writer(session).ensure_fts_connector()
    assert session.updates == []


def test_ensure_fts_hermaakt_wanneer_de_config_onleesbaar_is() -> None:
    """Onleesbare config betekent: we weten niet waarop hij indexeert — dus opnieuw bouwen.

    Dit gedrag is er na een echte storing gekomen. Bij de overgang naar de URN-namespace gaf
    listConnectors alleen de connectornaam terug; de code nam toen aan dat de config actueel was
    en liet de connector staan. Die bleef op de oude predicaten indexeren, waarna full-text
    zoeken stil nul treffers gaf — geen foutmelding, alleen lege antwoorden. Een herindexering
    van enkele seconden is dat risico niet waard.
    """
    session = _StubSession(rauw="bwb_tekst")
    _fts_writer(session).ensure_fts_connector()
    assert len(session.updates) == 2
    assert "dropConnector" in session.updates[0]
    assert "createConnector" in session.updates[1]


def test_ensure_fts_hermaakt_bij_gewijzigde_config() -> None:
    verouderd = _fts_connector_config(V)
    verouderd["fields"] = verouderd["fields"][:2]  # oude index met minder velden
    session = _StubSession(bestaande_config=verouderd)
    _fts_writer(session).ensure_fts_connector()
    assert len(session.updates) == 2
    assert "dropConnector" in session.updates[0]
    assert "createConnector" in session.updates[1]


def _bijlage_wet() -> Wet:
    return ToestandParser().parse(FIXTURES / "sample_bijlage.xml")


def test_bijlage_en_illustratie_nodes() -> None:
    wet = _bijlage_wet()
    g, summary = _writer().build_graph(wet)
    assert summary.bijlagen == 1
    assert summary.illustraties == 1
    # Bijlage-node met het gedeelde Citeerbaar-type + HEEFT_BIJLAGE vanaf de wet.
    bijlagen = list(g.subjects(RDF.type, V.ns.Bijlage))
    assert len(bijlagen) == 1
    bijlage = bijlagen[0]
    assert (bijlage, RDF.type, V.ns.Citeerbaar) in g
    assert (V.wet("BWBR0005537"), V.ns.heeftBijlage, bijlage) in g
    # De illustratie hangt via BEVAT_ILLUSTRATIE aan de tekstdrager (het lid).
    illustraties = list(g.subjects(RDF.type, V.ns.Illustratie))
    assert len(illustraties) == 1
    assert (illustraties[0], V.ns.naam, Literal("123954.png")) in g
    assert any(g.subjects(V.ns.bevatIllustratie, illustraties[0]))


def test_ondertekenaar_iri_valt_over_wetten_samen() -> None:
    # De ondertekenaar krijgt een wet-overstijgende slug-IRI, niet een wet-lokale
    # by_id-IRI: dezelfde persoon in een andere wet valt samen op dezelfde node.
    g, _ = _writer().build_graph(_bijlage_wet())
    ondertekenaars = list(g.subjects(RDF.type, V.ns.Ondertekenaar))
    assert len(ondertekenaars) == 1
    verwacht = V.entiteit("ondertekenaar", "De Minister van Justitie, E. M. H. Hirsch Ballin")
    assert ondertekenaars[0] == verwacht
    assert (V.wet("BWBR0005537"), V.ns.ondertekendDoor, verwacht) in g
