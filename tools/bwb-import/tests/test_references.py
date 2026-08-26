"""Tests voor verwijzingsherkenning (gestructureerd + tekst-fallback)."""

from __future__ import annotations

from lxml import etree

from app.models import VerwijzingSoort
from app.references import (
    detect_textual_references,
    extract_references,
    jci_doel,
    jci_doel_ref_key,
    jci_to_ref_key,
)


def _ankers(tekst: str, *, eigen_bwb_id: str = "BWBR0004770") -> list[str]:
    return [v.tekst for v in detect_textual_references(tekst, eigen_bwb_id=eigen_bwb_id)]


def test_jci_doel_ontleedt_bwb_artikel_lid() -> None:
    assert jci_doel("jci1.3:c:BWBR0005537&artikel=3:40") == ("BWBR0005537", "3:40", None)
    assert jci_doel("jci1.3:c:BWBR0004770&artikel=1&lid=2&z=2026-01-01") == (
        "BWBR0004770",
        "1",
        "2",
    )
    # Verwijzing naar een heel hoofdstuk: geen concreet artikel.
    assert jci_doel("jci1.3:c:BWBR0004770&hoofdstuk=I") == ("BWBR0004770", None, None)
    assert jci_doel(None) == (None, None, None)


def test_jci_to_ref_key_blijft_artikelniveau() -> None:
    # ref_key negeert het lid (lid-precisie zit op de relatie, niet de sleutel).
    assert jci_to_ref_key("jci1.3:c:BWBR0004770&artikel=1&lid=2") == "BWBR0004770#artikel=1"
    assert jci_to_ref_key("jci1.3:c:BWBR0004770&hoofdstuk=I") is None


def test_jci_geneste_divisie_neemt_laatste_artikel() -> None:
    # Geneste circulaire-divisies dragen het pad als herhaalde &artikel=-segmenten;
    # het laatste (meest specifieke) bepaalt het doel, zodat sub- en ouder-divisie
    # niet op dezelfde ref_key samenvallen.
    doc = "jci1.3:c:BWBR0024096&artikel=79&artikel=79.5a&z=2026-01-01&g=2026-01-01"
    assert jci_doel(doc) == ("BWBR0024096", "79.5a", None)
    assert jci_to_ref_key(doc) == "BWBR0024096#artikel=79.5a"


def test_detect_textual_references_spec_voorbeelden() -> None:
    assert _ankers("zie artikel 4 hierboven") == ["artikel 4"]
    assert _ankers("artikel 12a is van toepassing") == ["artikel 12a"]
    assert _ankers("op grond van artikel 10.1") == ["artikel 10.1"]
    assert _ankers("volgens artikel 3:2 Awb") == ["artikel 3:2 Awb"]
    assert _ankers("onrechtmatige daad (artikel 6:162 BW)") == ["artikel 6:162 BW"]


def test_detect_textual_references_resolutie() -> None:
    # Zonder afkorting: intern (eigen wet); met afkorting: via de map; BW per boek.
    (intern,) = detect_textual_references("zie artikel 4", eigen_bwb_id="BWBR0004770")
    assert intern.soort == VerwijzingSoort.TEKSTUEEL
    assert (intern.doel_bwb_id, intern.doel_artikel) == ("BWBR0004770", "4")
    (awb,) = detect_textual_references("volgens artikel 3:2 Awb", eigen_bwb_id="BWBR0004770")
    assert awb.doel_bwb_id == "BWBR0005537"
    (bw6,) = detect_textual_references("artikel 6:162 BW", eigen_bwb_id="BWBR0004770")
    assert bw6.doel_bwb_id == "BWBR0005289"
    # Onbekende afkorting: overslaan (te onzeker).
    assert detect_textual_references("artikel 3 Xyz", eigen_bwb_id="BWBR0004770") == []


def test_losse_woorden_niet_als_wet() -> None:
    # "en" mag niet als wetafkorting worden gezien.
    assert _ankers("artikel 4 en artikel 5") == ["artikel 4", "artikel 5"]


def test_jci_doel_ref_key_alle_niveaus() -> None:
    assert jci_doel_ref_key("jci1.3:c:BWBR0005537&artikel=3:40") == (
        "BWBR0005537#artikel=3:40",
        "artikel",
    )
    assert jci_doel_ref_key("jci1.3:c:BWBR0004770&hoofdstuk=I&artikel=1&lid=2&z=2026-01-01") == (
        "BWBR0004770#artikel=1#lid=2",
        "lid",
    )
    assert jci_doel_ref_key("jci1.3:c:BWBR0004770&hoofdstuk=I&artikel=2&lid=1&o=aa&o=1") == (
        "BWBR0004770#artikel=2#lid=1#o=aa#o=1",
        "onderdeel",
    )
    # Hele-structuur-doelen (voorheen gedropt).
    assert jci_doel_ref_key("jci1.3:c:BWBR0005537&titeldeel=4.1") == (
        "BWBR0005537#titeldeel=4.1",
        "titeldeel",
    )
    assert jci_doel_ref_key("jci1.3:c:BWBR0005537&hoofdstuk=6") == (
        "BWBR0005537#hoofdstuk=6",
        "hoofdstuk",
    )
    assert jci_doel_ref_key("jci1.3:c:BWBR0005537&afdeling=10.2.1") == (
        "BWBR0005537#afdeling=10.2.1",
        "afdeling",
    )
    # Hele wet.
    assert jci_doel_ref_key("jci1.3:c:BWBR0028093") == ("BWBR0028093", "wet")
    assert jci_doel_ref_key(None) == (None, None)
    assert jci_doel_ref_key("geen-jci") == (None, None)


def test_extract_references_intern_vs_extern() -> None:
    xml = """
    <lid>
      <al>Zie
        <intref bwb-id="BWBR0004770" doc="jci1.3:c:BWBR0004770&amp;artikel=4"
                bwb-ng-variabel-deel="/HoofdstukI/Artikel4">artikel 4</intref> en
        <extref bwb-id="BWBR0005537"
                doc="jci1.3:c:BWBR0005537&amp;artikel=3:40">artikel 3:40</extref>.
      </al>
    </lid>
    """
    element = etree.fromstring(xml)
    verwijzingen = extract_references(element, eigen_bwb_id="BWBR0004770")
    assert len(verwijzingen) == 2
    intern = next(v for v in verwijzingen if v.doel_bwb_id == "BWBR0004770")
    extern = next(v for v in verwijzingen if v.doel_bwb_id == "BWBR0005537")
    assert intern.soort == VerwijzingSoort.INTERN
    assert intern.doel_pad == "/HoofdstukI/Artikel4"
    assert extern.soort == VerwijzingSoort.EXTERN


def test_extref_naar_eigen_wet_is_intern() -> None:
    # Een extref naar de eigen wet wordt als intern beschouwd.
    xml = (
        '<lid><al><extref bwb-id="BWBR0004770" doc="jci1.3:c:BWBR0004770&amp;artikel=2">'
        "artikel 2</extref></al></lid>"
    )
    element = etree.fromstring(xml)
    (verwijzing,) = extract_references(element, eigen_bwb_id="BWBR0004770")
    assert verwijzing.soort == VerwijzingSoort.INTERN


def test_meta_data_verwijzingen_genegeerd() -> None:
    xml = """
    <lid>
      <al>Tekst zonder ref.</al>
      <meta-data><jcis>
        <extref bwb-id="BWBR9999999" doc="x">verborgen</extref>
      </jcis></meta-data>
    </lid>
    """
    element = etree.fromstring(xml)
    assert extract_references(element, eigen_bwb_id="BWBR0004770") == []
