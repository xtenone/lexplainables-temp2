"""Tests voor validate_analyse.py — de mechanische pre-check vóór de review-server.

Exitcodes: 0 = schoon, 1 = waarschuwingen, 2 = blokkerende fouten / onleesbaar.
Stdlib-only (unittest + subprocess).

De analyse-eenheid is het werkgebied met meerdere bronnen: activiteit 2 draagt `bronnen[]`,
activiteit 3 is werkgebied-breed (gedeelde begrippen/afleidingsregels met `vindplaatsen`).
"""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "validate_analyse.py"

# Volledig valide activiteit-2-analyse (werkgebied met één bron): geen fouten én geen
# waarschuwingen → exit 0.
GELDIG_ACT2 = {
    "werkgebied": {"naam": "Testwerkgebied", "hoofdvraag": "test"},
    "analysefocus": "test",
    "bronnen": [
        {
            "bron_id": "br1",
            "label": "Wet X art. 1",
            "bwbId": "BWBR9999999",
            "artikel": "1",
            "bronreferentie": "jci1.3:c:BWBR9999999&artikel=1",
            "leden": [{"lid": "1", "tekst": "De belastingplichtige doet aangifte."}],
            "markeringen": [
                {
                    "id": "m1",
                    "bron_id": "br1",
                    "klasse": "Rechtssubject",
                    "formulering": "De belastingplichtige",
                    "vindplaats": "lid 1",
                }
            ],
            "verwijzingen": [],
        }
    ],
}


def _mark(data):
    """Snelkoppeling naar de eerste markering van de eerste bron."""
    return data["bronnen"][0]["markeringen"][0]


def _run(data_or_text, activiteit: str = "2", act2=None, begrippenlijst=None) -> int:
    with tempfile.TemporaryDirectory() as d:
        pad = Path(d) / "analyse.json"
        if isinstance(data_or_text, str):
            pad.write_text(data_or_text, encoding="utf-8")
        else:
            pad.write_text(json.dumps(data_or_text), encoding="utf-8")
        cmd = [sys.executable, str(SCRIPT), "--input", str(pad), "--activiteit", activiteit]
        if act2 is not None:
            act2_pad = Path(d) / "act2.json"
            act2_pad.write_text(json.dumps(act2), encoding="utf-8")
            cmd += ["--act2", str(act2_pad)]
        if begrippenlijst is not None:
            bl_pad = Path(d) / "begrippenlijst.json"
            bl_pad.write_text(json.dumps(begrippenlijst), encoding="utf-8")
            cmd += ["--begrippenlijst", str(bl_pad)]
        res = subprocess.run(cmd, text=True, capture_output=True, timeout=15)
        return res.returncode


class ValidateAnalyseTest(unittest.TestCase):
    def test_geldige_analyse_exit_0(self):
        self.assertEqual(_run(GELDIG_ACT2, "2"), 0)

    def test_ongeldige_jas_klasse_blokkeert(self):
        data = copy.deepcopy(GELDIG_ACT2)
        _mark(data)["klasse"] = "VerzonnenKlasse"
        self.assertEqual(_run(data, "2"), 2)

    def test_dubbele_ids_over_bronnen_blokkeren(self):
        # Werkgebied-brede id-uniciteit: hetzelfde id in een tweede bron is fout.
        data = copy.deepcopy(GELDIG_ACT2)
        tweede = copy.deepcopy(data["bronnen"][0])
        tweede["bron_id"] = "br2"
        tweede["label"] = "Wet X art. 2"
        tweede["markeringen"][0]["bron_id"] = "br2"   # id blijft 'm1' → botsing
        data["bronnen"].append(tweede)
        self.assertEqual(_run(data, "2"), 2)

    def test_bron_id_mismatch_blokkeert(self):
        data = copy.deepcopy(GELDIG_ACT2)
        _mark(data)["bron_id"] = "br9"   # wijkt af van de bron 'br1'
        self.assertEqual(_run(data, "2"), 2)

    def test_ontbrekende_bronreferentie_blokkeert(self):
        data = copy.deepcopy(GELDIG_ACT2)
        data["bronnen"][0]["bronreferentie"] = ""
        self.assertEqual(_run(data, "2"), 2)

    def test_geen_bronnen_blokkeert(self):
        data = copy.deepcopy(GELDIG_ACT2)
        data["bronnen"] = []
        self.assertEqual(_run(data, "2"), 2)

    def test_malformed_json_blokkeert(self):
        self.assertEqual(_run("{ dit is geen geldige json", "2"), 2)

    def test_ontbrekend_bestand_blokkeert(self):
        res = subprocess.run(
            [sys.executable, str(SCRIPT), "--input", "/bestaat/echt/niet.json", "--activiteit", "2"],
            text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(res.returncode, 2)

    def test_ellips_citaat_geen_waarschuwing(self):
        data = copy.deepcopy(GELDIG_ACT2)
        data["bronnen"][0]["leden"][0]["tekst"] = "De belastingschuldige kan niet meer dan een bankrekening bestemmen."
        _mark(data)["formulering"] = "De belastingschuldige kan ... een bankrekening bestemmen"
        self.assertEqual(_run(data, "2"), 0)

    def test_vierkante_haken_geen_waarschuwing(self):
        data = copy.deepcopy(GELDIG_ACT2)
        data["bronnen"][0]["leden"][0]["tekst"] = "De belastingschuldige bestemt een bankrekening."
        _mark(data)["formulering"] = "een [bankrekening]"
        self.assertEqual(_run(data, "2"), 0)

    def test_echt_niet_letterlijk_citaat_blokkeert(self):
        # Citaat-mismatch is een blokkerende fout (brongetrouwheid), geen waarschuwing meer.
        data = copy.deepcopy(GELDIG_ACT2)
        _mark(data)["formulering"] = "de belastingbetaler verzint iets"
        self.assertEqual(_run(data, "2"), 2)

    def test_citaat_geheel_tussen_haken_blokkeert(self):
        # Een formulering die volledig uit invoegingen bestaat ('[…]') citeert niets.
        data = copy.deepcopy(GELDIG_ACT2)
        _mark(data)["formulering"] = "[een parafrase zonder één letterlijk fragment]"
        self.assertEqual(_run(data, "2"), 2)

    def test_citaat_alleen_ellips_blokkeert(self):
        data = copy.deepcopy(GELDIG_ACT2)
        _mark(data)["formulering"] = "..."
        self.assertEqual(_run(data, "2"), 2)

    def test_citaat_uit_ander_lid_dan_vindplaats_blokkeert(self):
        # De toets loopt tegen het lid dat de vindplaats claimt, niet tegen de concatenatie:
        # een citaat uit lid 2 met vindplaats "lid 1" is een verkeerde herleiding.
        data = copy.deepcopy(GELDIG_ACT2)
        data["bronnen"][0]["leden"].append(
            {"lid": "2", "tekst": "De inspecteur stelt de aanslag vast."}
        )
        _mark(data)["formulering"] = "De inspecteur stelt de aanslag vast"
        _mark(data)["vindplaats"] = "lid 1"
        self.assertEqual(_run(data, "2"), 2)

    def test_citaat_uit_geclaimd_lid_exit_0(self):
        data = copy.deepcopy(GELDIG_ACT2)
        data["bronnen"][0]["leden"].append(
            {"lid": "2", "tekst": "De inspecteur stelt de aanslag vast."}
        )
        _mark(data)["formulering"] = "De inspecteur stelt de aanslag vast"
        _mark(data)["vindplaats"] = "lid 2"
        self.assertEqual(_run(data, "2"), 0)

    def test_geldige_act3_exit_0(self):
        self.assertEqual(_run(GELDIG_ACT3, "3"), 0)

    def test_ongeldig_regeltype_act3_blokkeert(self):
        data = copy.deepcopy(GELDIG_ACT3)
        data["afleidingsregels"][0]["type"] = "onzinregel"
        self.assertEqual(_run(data, "3"), 2)


GELDIG_ACT3 = {
    "werkgebied": {"naam": "Testwerkgebied"},
    "bronnen": [{"bron_id": "br1", "label": "Wet X art. 1"}],
    "begrippen": [
        {"id": "b1", "naam": "belastingplichtige", "klasse": "Rechtssubject",
         "definitie": "drager van rechten en plichten in de aangifte",
         "vindplaatsen": [{"bron_id": "br1", "lid": "1"}]},
        {"id": "b2", "naam": "verschuldigde belasting", "klasse": "Variabele en variabelewaarde",
         "definitie": "het bedrag dat moet worden voldaan",
         "vindplaatsen": [{"bron_id": "br1", "lid": "1"}]},
        {"id": "b3", "naam": "grondslag", "klasse": "Variabele en variabelewaarde",
         "definitie": "het bedrag waarover wordt geheven",
         "vindplaatsen": [{"bron_id": "br1", "lid": "1"}]},
    ],
    "afleidingsregels": [
        {"id": "r1", "naam": "berekenen verschuldigde belasting", "type": "rekenregel",
         "uitvoer": {"begrip_id": "b2", "toelichting": ""},
         "invoer": [{"begrip_id": "b3", "toelichting": ""}],
         "parameters": [],
         "voorwaarden": [{"tekst": "de belastingplichtige doet aangifte",
                          "begrip_ids": ["b1"], "verbinding": ""}],
         "vindplaatsen": [{"bron_id": "br1", "lid": "1"}]},
    ],
}


class ValidateAct3Test(unittest.TestCase):
    """Nieuwe act-3-checks: begrip-id-referenties, naam-uniciteit, dekking en herkomst."""

    def test_regel_zonder_uitvoer_begrip_blokkeert(self):
        data = copy.deepcopy(GELDIG_ACT3)
        data["afleidingsregels"][0]["uitvoer"] = {"begrip_id": "", "toelichting": ""}
        self.assertEqual(_run(data, "3"), 2)

    def test_dangling_uitvoer_begrip_blokkeert(self):
        data = copy.deepcopy(GELDIG_ACT3)
        data["afleidingsregels"][0]["uitvoer"]["begrip_id"] = "b99"
        self.assertEqual(_run(data, "3"), 2)

    def test_dangling_invoer_begrip_blokkeert(self):
        data = copy.deepcopy(GELDIG_ACT3)
        data["afleidingsregels"][0]["invoer"].append({"begrip_id": "b42", "toelichting": ""})
        self.assertEqual(_run(data, "3"), 2)

    def test_dangling_voorwaarde_begrip_blokkeert(self):
        data = copy.deepcopy(GELDIG_ACT3)
        data["afleidingsregels"][0]["voorwaarden"][0]["begrip_ids"] = ["b42"]
        self.assertEqual(_run(data, "3"), 2)

    def test_dangling_verwijst_naar_begrippen_blokkeert(self):
        data = copy.deepcopy(GELDIG_ACT3)
        data["begrippen"][0]["verwijst_naar_begrippen"] = ["b42"]
        self.assertEqual(_run(data, "3"), 2)

    def test_dangling_relatie_doel_blokkeert(self):
        data = copy.deepcopy(GELDIG_ACT3)
        data["begrippen"][0]["relaties"] = [
            {"soort": "relatie", "beschrijving": "hoort bij", "doel_begrip": "b42"}
        ]
        self.assertEqual(_run(data, "3"), 2)

    def test_geldige_relatie_en_verwijzing_exit_0(self):
        data = copy.deepcopy(GELDIG_ACT3)
        data["begrippen"][0]["verwijst_naar_begrippen"] = ["b2"]
        data["begrippen"][0]["relaties"] = [
            {"soort": "relatie", "beschrijving": "is schuldenaar van", "doel_begrip": "b2"},
            {"soort": "kenmerk", "beschrijving": "leeftijd", "doel_begrip": None},
        ]
        self.assertEqual(_run(data, "3"), 0)

    def test_dubbele_begripsnaam_blokkeert(self):
        data = copy.deepcopy(GELDIG_ACT3)
        data["begrippen"][1]["naam"] = "Belastingplichtige "   # genormaliseerd gelijk aan b1
        self.assertEqual(_run(data, "3"), 2)

    def test_regelnaam_zonder_werkwoordsvorm_waarschuwt(self):
        data = copy.deepcopy(GELDIG_ACT3)
        data["afleidingsregels"][0]["naam"] = "verschuldigde belasting"
        self.assertEqual(_run(data, "3"), 1)

    def test_begripsnaam_met_lidwoord_waarschuwt(self):
        data = copy.deepcopy(GELDIG_ACT3)
        data["begrippen"][2]["naam"] = "de grondslag"
        self.assertEqual(_run(data, "3"), 1)

    def test_begripsnaam_in_eigen_definitie_waarschuwt(self):
        data = copy.deepcopy(GELDIG_ACT3)
        data["begrippen"][2]["definitie"] = "de grondslag waarover wordt geheven"
        self.assertEqual(_run(data, "3"), 1)

    def test_regel_zonder_invoer_en_parameters_waarschuwt(self):
        data = copy.deepcopy(GELDIG_ACT3)
        data["afleidingsregels"][0]["invoer"] = []
        self.assertEqual(_run(data, "3"), 1)

    def test_gedeelde_grondformulering_waarschuwt(self):
        data = copy.deepcopy(GELDIG_ACT3)
        data["begrippen"][1]["grondformulering"] = "belasting"
        data["begrippen"][2]["grondformulering"] = "belasting"
        self.assertEqual(_run(data, "3"), 1)

    def test_dekking_met_act2_dangling_markering_blokkeert(self):
        data = copy.deepcopy(GELDIG_ACT3)
        data["begrippen"][0]["markering_ids"] = ["m99"]
        self.assertEqual(_run(data, "3", act2=GELDIG_ACT2), 2)

    def test_dekking_ongedekte_markering_waarschuwt(self):
        # GELDIG_ACT2 heeft markering m1 (Rechtssubject, begrip-plichtig) die nergens landt.
        self.assertEqual(_run(GELDIG_ACT3, "3", act2=GELDIG_ACT2), 1)

    def test_dekking_gedekte_markering_exit_0(self):
        data = copy.deepcopy(GELDIG_ACT3)
        data["begrippen"][0]["markering_ids"] = ["m1"]
        self.assertEqual(_run(data, "3", act2=GELDIG_ACT2), 0)

    def test_herkomst_ontbreekt_bij_begrippenlijst_waarschuwt(self):
        lijst = {"begrippen": [{"id": "ab1", "naam": "belastingplichtige"}]}
        self.assertEqual(_run(GELDIG_ACT3, "3", begrippenlijst=lijst), 1)

    def test_herkomst_geldig_exit_0(self):
        lijst = {"begrippen": [{"id": "ab1", "naam": "belastingplichtige"}]}
        data = copy.deepcopy(GELDIG_ACT3)
        data["begrippen"][0]["herkomst"] = {"status": "hergebruikt", "aangeleverd_id": "ab1"}
        data["begrippen"][1]["herkomst"] = {"status": "nieuw"}
        data["begrippen"][2]["herkomst"] = {"status": "nieuw"}
        self.assertEqual(_run(data, "3", begrippenlijst=lijst), 0)

    def test_herkomst_aangepast_zonder_motivatie_waarschuwt(self):
        lijst = {"begrippen": [{"id": "ab1", "naam": "belastingplichtige"}]}
        data = copy.deepcopy(GELDIG_ACT3)
        data["begrippen"][0]["herkomst"] = {"status": "aangepast", "aangeleverd_id": "ab1"}
        data["begrippen"][1]["herkomst"] = {"status": "nieuw"}
        data["begrippen"][2]["herkomst"] = {"status": "nieuw"}
        self.assertEqual(_run(data, "3", begrippenlijst=lijst), 1)

    def test_herkomst_dangling_aangeleverd_id_blokkeert(self):
        # Herkomst-structuurfouten blokkeren: een dangling aangeleverd_id maakt het
        # hergebruik oncontroleerbaar.
        lijst = {"begrippen": [{"id": "ab1", "naam": "belastingplichtige"}]}
        data = copy.deepcopy(GELDIG_ACT3)
        data["begrippen"][0]["herkomst"] = {"status": "hergebruikt", "aangeleverd_id": "ab9"}
        data["begrippen"][1]["herkomst"] = {"status": "nieuw"}
        data["begrippen"][2]["herkomst"] = {"status": "nieuw"}
        self.assertEqual(_run(data, "3", begrippenlijst=lijst), 2)

    def test_herkomst_onbekende_status_blokkeert(self):
        lijst = {"begrippen": [{"id": "ab1", "naam": "belastingplichtige"}]}
        data = copy.deepcopy(GELDIG_ACT3)
        data["begrippen"][0]["herkomst"] = {"status": "overgetypt"}
        data["begrippen"][1]["herkomst"] = {"status": "nieuw"}
        data["begrippen"][2]["herkomst"] = {"status": "nieuw"}
        self.assertEqual(_run(data, "3", begrippenlijst=lijst), 2)

    def test_herkomst_zonder_aangeleverd_id_blokkeert(self):
        lijst = {"begrippen": [{"id": "ab1", "naam": "belastingplichtige"}]}
        data = copy.deepcopy(GELDIG_ACT3)
        data["begrippen"][0]["herkomst"] = {"status": "hergebruikt"}
        data["begrippen"][1]["herkomst"] = {"status": "nieuw"}
        data["begrippen"][2]["herkomst"] = {"status": "nieuw"}
        self.assertEqual(_run(data, "3", begrippenlijst=lijst), 2)

    def test_herkomst_aangepast_zonder_motivatie_waarschuwt(self):
        # Ontbrekende motivatie blijft een (inhoudelijke) waarschuwing, geen structuurfout.
        lijst = {"begrippen": [{"id": "ab1", "naam": "belastingplichtige"}]}
        data = copy.deepcopy(GELDIG_ACT3)
        data["begrippen"][0]["herkomst"] = {"status": "aangepast", "aangeleverd_id": "ab1"}
        data["begrippen"][1]["herkomst"] = {"status": "nieuw"}
        data["begrippen"][2]["herkomst"] = {"status": "nieuw"}
        self.assertEqual(_run(data, "3", begrippenlijst=lijst), 1)

    def test_ongeldige_klasse_op_begrip_blokkeert(self):
        # Spiegel van act-2: een verzonnen JAS-klasse blokkeert ook op een begrip.
        data = copy.deepcopy(GELDIG_ACT3)
        data["begrippen"][0]["klasse"] = "Verzonnen klasse"
        self.assertEqual(_run(data, "3"), 2)

    def test_invoer_item_zonder_begrip_id_blokkeert(self):
        data = copy.deepcopy(GELDIG_ACT3)
        data["afleidingsregels"][0]["invoer"] = [{"toelichting": "zonder begrip_id"}]
        self.assertEqual(_run(data, "3"), 2)

    def test_parameter_item_zonder_begrip_id_blokkeert(self):
        data = copy.deepcopy(GELDIG_ACT3)
        data["afleidingsregels"][0]["parameters"] = [{"waarde": "5%", "toelichting": "x"}]
        self.assertEqual(_run(data, "3"), 2)

    def test_synoniem_botst_met_andere_begripsnaam_blokkeert(self):
        data = copy.deepcopy(GELDIG_ACT3)
        data["begrippen"][1]["synoniemen"] = ["Belastingplichtige"]  # = naam van b1
        self.assertEqual(_run(data, "3"), 2)

    def test_synoniem_gelijk_aan_eigen_naam_waarschuwt(self):
        data = copy.deepcopy(GELDIG_ACT3)
        data["begrippen"][0]["synoniemen"] = ["belastingplichtige"]
        self.assertEqual(_run(data, "3"), 1)


if __name__ == "__main__":
    unittest.main()
