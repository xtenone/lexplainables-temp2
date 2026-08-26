"""Tests voor de toestand-parser."""

from __future__ import annotations

from pathlib import Path

from app.models import Wet
from app.parser import ToestandParser


def _parse(sample_xml: Path) -> Wet:
    return ToestandParser().parse(sample_xml)


def test_metadata(sample_xml: Path) -> None:
    wet = _parse(sample_xml)
    assert wet.bwb_id == "BWBR0004770"
    assert wet.citeertitel == "Invorderingswet 1990"
    assert wet.soort == "wet"
    assert wet.opschrift.startswith("Wet van 30 mei 1990")
    assert wet.geldig_vanaf == "2026-01-01"


def test_structuur(sample_xml: Path) -> None:
    wet = _parse(sample_xml)
    # De fixture bevat één hoofdstuk met twee artikelen.
    assert len(wet.structuurdelen) == 1
    hoofdstuk = wet.structuurdelen[0]
    assert hoofdstuk.soort == "hoofdstuk"
    assert hoofdstuk.nummer == "I"
    assert hoofdstuk.id == "BWBR0004770/HoofdstukI"
    assert len(hoofdstuk.artikelen) == 2


def test_artikel_en_leden(sample_xml: Path) -> None:
    wet = _parse(sample_xml)
    artikel1 = wet.structuurdelen[0].artikelen[0]
    assert artikel1.id == "BWBR0004770/HoofdstukI/Artikel1"
    assert artikel1.nummer == "1"
    assert len(artikel1.leden) == 2
    lid1 = artikel1.leden[0]
    assert lid1.nummer == "1"
    assert lid1.id == "BWBR0004770/HoofdstukI/Artikel1/Lid1"
    assert "invordering van rijksbelastingen" in lid1.tekst
    # Tekst van een artikel met leden bevat geen meta-data-rommel.
    assert "jci1.3" not in lid1.tekst


def test_verwijzingen_uit_xml(sample_xml: Path) -> None:
    wet = _parse(sample_xml)
    lid2 = wet.structuurdelen[0].artikelen[0].leden[1]
    # Lid 2 van artikel 1 verwijst extern naar de Awb (BWBR0005537).
    doelen = {v.doel_bwb_id for v in lid2.verwijzingen}
    assert "BWBR0005537" in doelen
    assert all(v.soort.value in {"intref", "extref"} for v in lid2.verwijzingen)


def test_artikel_provenance(sample_xml: Path) -> None:
    artikel1 = _parse(sample_xml).structuurdelen[0].artikelen[0]
    assert artikel1.inwerking == "2009-07-01"
    assert artikel1.bron == "Stb.2009-265"
    assert artikel1.effect == "wijziging"
    assert artikel1.status == "goed"
    assert artikel1.jci is not None and artikel1.jci.startswith("jci1.3:")


def test_lid_jci_tot_lidniveau(sample_xml: Path) -> None:
    lid1 = _parse(sample_xml).structuurdelen[0].artikelen[0].leden[0]
    assert lid1.jci is not None
    assert "&lid=1" in lid1.jci


def test_wet_brondata(sample_xml: Path) -> None:
    wet = _parse(sample_xml)
    assert wet.publicatiejaar == "2018"
    assert wet.publicatienr == "75"
    assert wet.ondertekeningsdatum == "2018-02-21"
    assert wet.dossier == "34753"


def test_onderdelen_en_nesting(sample_xml: Path) -> None:
    wet = _parse(sample_xml)
    # Artikel 2 (definitieartikel) heeft per lid een lijst met onderdelen.
    artikel2 = wet.structuurdelen[0].artikelen[1]
    lid1 = artikel2.leden[0]
    assert len(lid1.onderdelen) > 5
    onderdeel_a = lid1.onderdelen[0]
    assert onderdeel_a.nummer == "a."
    assert "rijksbelastingen" in onderdeel_a.tekst
    # Een onderdeel kan zelf weer onderdelen bevatten (geneste lijst).
    assert any(o.subonderdelen for o in lid1.onderdelen)
    # Onderdelen dragen hun eigen verwijzingen.
    assert any(o.verwijzingen for o in lid1.onderdelen)


def test_onderdeel_tekst_niet_in_lid(sample_xml: Path) -> None:
    # Onderdeel-tekst hoort bij het onderdeel-node, niet (dubbel) in de lid-tekst.
    lid1 = _parse(sample_xml).structuurdelen[0].artikelen[1].leden[0]
    onderdeel_tekst = lid1.onderdelen[2].tekst  # bv. "Douanewetboek van de Unie: ..."
    assert onderdeel_tekst
    assert onderdeel_tekst not in lid1.tekst


def test_aanhef_en_considerans(sample_xml: Path) -> None:
    wet = _parse(sample_xml)
    assert wet.aanhef is not None and wet.aanhef.startswith("Wij Beatrix")
    assert "Raad van State gehoord" in wet.aanhef
    assert wet.considerans is not None
    assert "in overweging genomen" in wet.considerans


def test_definities_uit_nadruk(sample_xml: Path) -> None:
    # Artikel 2 lid 1: elke definitie begint met een cursieve term + dubbele punt;
    # geneste onderdelen (aa -> 1°..4°) dragen hun eigen begrippen.
    lid1 = _parse(sample_xml).structuurdelen[0].artikelen[1].leden[0]

    def alle_begrippen(onderdelen) -> list[str]:
        begrippen: list[str] = []
        for o in onderdelen:
            begrippen.extend(o.definieert_begrippen)
            begrippen.extend(alle_begrippen(o.subonderdelen))
        return begrippen

    begrippen = alle_begrippen(lid1.onderdelen)
    assert {"rijksbelastingen", "Koninkrijk", "Rijk", "Nederland", "BES eilanden"} <= set(begrippen)
    # Cursieve niet-definities (bv. "Stb." middenin een zin) tellen niet mee.
    assert "Stb." not in begrippen


def test_noot_niet_in_tekst_maar_als_voetnoot(sample_tabel_xml: Path) -> None:
    artikel = _parse(sample_tabel_xml).structuurdelen[0].artikelen[0]
    assert "hoort niet in de lopende tekst" not in artikel.tekst
    assert len(artikel.voetnoten) == 1
    assert "hoort niet in de lopende tekst" in artikel.voetnoten[0]


def test_tabel_tekst_leesbaar(sample_tabel_xml: Path) -> None:
    artikel = _parse(sample_tabel_xml).structuurdelen[0].artikelen[0]
    # De lopende tekst blijft vooraan; de tabel volgt als leesbare rijen.
    assert artikel.tekst.startswith("De tarieven staan in de volgende tabel")
    assert "Categorie | Tarief" in artikel.tekst
    assert "A | 10%" in artikel.tekst
    assert "B | 20%" in artikel.tekst


# --------------------------------------------------------------- circulaires
def test_circulaire_divisie_structuur(sample_circulaire_xml: Path) -> None:
    wet = _parse(sample_circulaire_xml)
    # Circulaire heeft geen wettekst-structuurdelen/artikelen maar een divisie-boom.
    assert wet.soort == "circulaire"
    assert not wet.structuurdelen and not wet.losse_artikelen
    assert len(wet.divisies) == 1
    top = wet.divisies[0]
    assert top.nummer == "1"
    assert top.label == "Artikel 1"
    assert top.titel == "Inleiding"
    assert top.inwerking == "2020-01-01"
    assert top.jci == "jci1.3:c:BWBR0099999&artikel=1"
    # Eigen tekst, maar zonder de tekst van de subdivisie of het onderdeel.
    assert "Deze leidraad ziet op" in top.tekst
    assert "subtekst" not in top.tekst.lower()
    assert len(top.subdivisies) == 1
    assert top.subdivisies[0].nummer == "1.1"


def test_circulaire_verwijzingen_en_onderdelen(sample_circulaire_xml: Path) -> None:
    top = _parse(sample_circulaire_xml).divisies[0]
    # Divisie-niveau verwijst naar de Invorderingswet; het onderdeel naar de Awr.
    docs = {v.doc for v in top.verwijzingen}
    assert "jci1.3:c:BWBR0004770&artikel=4" in docs
    # De verwijzing binnen het onderdeel telt niet dubbel op divisie-niveau.
    assert "jci1.3:c:BWBR0002320&artikel=1" not in docs
    assert len(top.onderdelen) == 1
    assert top.onderdelen[0].nummer == "a."
    assert any(v.doc == "jci1.3:c:BWBR0002320&artikel=1" for v in top.onderdelen[0].verwijzingen)


# ------------------------------------------------- ministeriële regelingen
def test_regeling_structuur(sample_regeling_xml: Path) -> None:
    wet = _parse(sample_regeling_xml)
    # Een <regeling>/<regeling-tekst> parseert als een gewone wettekst.
    assert wet.soort == "ministeriele-regeling"
    assert wet.citeertitel == "Testuitvoeringsregeling 1990"
    assert len(wet.structuurdelen) == 1
    hoofdstuk = wet.structuurdelen[0]
    assert hoofdstuk.soort == "hoofdstuk"
    assert hoofdstuk.nummer == "I"
    artikel = hoofdstuk.artikelen[0]
    assert artikel.nummer == "1"
    assert len(artikel.leden) == 1
    assert "uitvoering aan" in artikel.leden[0].tekst
    assert any(v.doc == "jci1.3:c:BWBR0004770&artikel=31" for v in artikel.leden[0].verwijzingen)


def test_regeling_aanhef(sample_regeling_xml: Path) -> None:
    wet = _parse(sample_regeling_xml)
    # Regeling-aanhef opent met <wie> in plaats van <wij>.
    assert wet.aanhef is not None
    assert wet.aanhef.startswith("De Staatssecretaris van Financiën")
    assert "Besluit:" in wet.aanhef
    assert wet.considerans is not None
    assert wet.considerans.startswith("Gelet op")


def test_ondertekenaars(sample_xml: Path) -> None:
    wet = _parse(sample_xml)
    # De fixture heeft drie <ondertekening>-blokken (2 in de wetsluiting, 1 in de
    # uitgifte), met verschillende functies -> drie ondertekenaars.
    functies = {o.functie for o in wet.ondertekenaars}
    assert "De Staatssecretaris van Financiën," in functies
    assert "De Minister van Justitie," in functies
    assert len(wet.ondertekenaars) == 3
    financien = next(o for o in wet.ondertekenaars if "Financiën" in (o.functie or ""))
    assert financien.achternaam == "M. J. J. van Amelsvoort"


def test_bijlage(sample_bijlage_xml: Path) -> None:
    wet = _parse(sample_bijlage_xml)
    assert len(wet.bijlagen) == 1
    bijlage = wet.bijlagen[0]
    assert bijlage.id == "BWBR0005537/Bijlage1"
    assert bijlage.label == "Bijlage"
    assert bijlage.nummer == "1"
    assert bijlage.titel == "Regeling rechtstreeks beroep"
    assert "Tegen een besluit" in bijlage.tekst
    # Eigen tekst van de bijlage bevat niet de tekst van een genest artikel.
    assert "situatietekening" not in bijlage.tekst
    # Bijlage heeft een onderdeel (lijst/li) en een eigen artikel.
    assert len(bijlage.onderdelen) == 1
    assert bijlage.onderdelen[0].nummer == "a."
    assert len(bijlage.artikelen) == 1
    assert bijlage.artikelen[0].id == "BWBR0005537/Bijlage1/Artikel1"
    # Verwijzing op bijlage-niveau (extref naar de Archiefwet).
    assert any(v.doel_bwb_id == "BWBR0007376" for v in bijlage.verwijzingen)


def test_terugwerkende_kracht(sample_bijlage_xml: Path) -> None:
    wet = _parse(sample_bijlage_xml)
    # De bijlage heeft een terugwerkend.datum in zijn inwerkingtredings-metadata.
    assert wet.bijlagen[0].terugwerkend_tot == "2025-07-01"
    # Een tekstdeel zonder terugwerkende kracht laat het veld leeg.
    assert wet.structuurdelen == []  # geen structuur in deze fixture
    assert wet.bijlagen[0].artikelen[0].terugwerkend_tot is None


def test_illustratie(sample_bijlage_xml: Path) -> None:
    wet = _parse(sample_bijlage_xml)
    # De illustratie zit in een lid van het bijlage-artikel.
    lid = wet.bijlagen[0].artikelen[0].leden[0]
    assert len(lid.illustraties) == 1
    illustratie = lid.illustraties[0]
    assert illustratie.id == "123954"
    assert illustratie.naam == "123954.png"
    assert illustratie.formaat == "png"
    assert illustratie.breedte == "1417px"
    assert illustratie.hoogte == "364px"
