"""Tests voor validate_regelspraak.py — de mechanische pre-check vóór de review-server.

Stdlib-only (unittest + subprocess). De nadruk ligt op de gebruik-scan (stap `regels`):
een gedeclareerde parameter/objecttype dat door geen regel wordt aangeroepen, levert een
niet-blokkerende waarschuwing (exit 1) — het faalpatroon van de art. 9-output waar zeven
termijn-parameters ongebruikt bleven. Bestaande blokkerende checks (exit 2) blijven werken.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "validate_regelspraak.py"


def _regel(rid: str, naam: str, tekst: str) -> dict:
    return {
        "id": rid,
        "naam": naam,
        "soort": "kenmerktoekenning",
        "regelspraak_tekst": tekst,
        "herkomst": {"regel_id": "r1", "vindplaatsen": [{"bron_id": "br1", "lid": "1"}]},
    }


def _model(regels: list[dict], parameters: list[str], objecttypen: list[str]) -> dict:
    return {
        "werkgebied": {"naam": "Test"},
        "gegevensspraak_index": {
            "objecttypen": [{"naam": n} for n in objecttypen],
            "parameters": [{"naam": n} for n in parameters],
        },
        "regels": regels,
    }


def _run(model: dict) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as d:
        mp = Path(d) / "model.json"
        mp.write_text(json.dumps(model), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--input", str(mp), "--stap", "regels"],
            capture_output=True, text=True,
        )
        return proc.returncode, proc.stdout + proc.stderr


class GebruikScanTest(unittest.TestCase):
    def test_ongebruikte_parameter_geeft_waarschuwing_exit1(self):
        model = _model(
            regels=[_regel("rs1", "Iets", "Regel Iets\n  geldig altijd\n    Een belastingaanslag is invorderbaar.")],
            parameters=["de invorderingstermijn naheffingsaanslag"],
            objecttypen=["belastingaanslag"],
        )
        code, out = _run(model)
        self.assertEqual(code, 1)
        self.assertIn("de invorderingstermijn naheffingsaanslag", out)
        self.assertIn("door geen regel gebruikt", out)

    def test_gebruikte_parameter_geen_waarschuwing(self):
        tekst = (
            "Regel Termijn\n  geldig altijd\n    De vervaldatum van een belastingaanslag moet "
            "berekend worden als de dagtekening plus de invorderingstermijn naheffingsaanslag."
        )
        model = _model(
            regels=[_regel("rs1", "Termijn", tekst)],
            parameters=["de invorderingstermijn naheffingsaanslag"],
            objecttypen=["belastingaanslag"],
        )
        code, out = _run(model)
        self.assertEqual(code, 0)
        self.assertNotIn("door geen regel gebruikt", out)

    def test_ongebruikt_objecttype_geeft_waarschuwing(self):
        tekst = "Regel Iets\n  geldig altijd\n    Een belastingaanslag is invorderbaar."
        model = _model(
            regels=[_regel("rs1", "Iets", tekst)],
            parameters=[],
            objecttypen=["belastingaanslag", "aanslagbiljet"],
        )
        code, out = _run(model)
        self.assertEqual(code, 1)
        self.assertIn("Objecttype 'aanslagbiljet'", out)
        self.assertNotIn("Objecttype 'belastingaanslag'", out)

    def test_blokkerende_fout_blijft_exit2(self):
        # Ongeldige regel-soort = blokkerende fout; gaat vóór de niet-blokkerende usage-scan.
        regel = _regel("rs1", "Iets", "Regel Iets\n  geldig altijd\n    Een belastingaanslag is invorderbaar.")
        regel["soort"] = "onbestaande-soort"
        model = _model(regels=[regel], parameters=[], objecttypen=["belastingaanslag"])
        code, out = _run(model)
        self.assertEqual(code, 2)
        self.assertIn("Ongeldige regel-soort", out)


def _ingest() -> dict:
    return {
        "werkgebied": {"naam": "Test"},
        "bronnen": [{"bron_id": "br1", "label": "Wet art. 1"}],
        "begrippen": [
            {"id": "b1", "naam": "belastingaanslag"},
            {"id": "b2", "naam": "vervaldatum"},
        ],
        "afleidingsregels": [
            {"id": "r1", "naam": "bepalen vervaldatum"},
        ],
    }


def _gs_model(objecttypen: list[dict]) -> dict:
    return {"werkgebied": {"naam": "Test"}, "gegevensspraak": {"objecttypen": objecttypen}}


def _ot(naam: str, begrip_ids: list[str], bron_id: str = "br1") -> dict:
    return {
        "id": "ot1",
        "naam": naam,
        "datatype": "",
        "regelspraak_tekst": f"Objecttype de {naam}",
        "herkomst": {"begrip_ids": begrip_ids, "vindplaatsen": [{"bron_id": bron_id, "lid": "1"}]},
    }


def _run_ingest(model: dict, stap: str, ingest: dict | None) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as d:
        mp = Path(d) / "model.json"
        mp.write_text(json.dumps(model), encoding="utf-8")
        cmd = [sys.executable, str(SCRIPT), "--input", str(mp), "--stap", stap]
        if ingest is not None:
            ip = Path(d) / "ingest.json"
            ip.write_text(json.dumps(ingest), encoding="utf-8")
            cmd += ["--ingest", str(ip)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return proc.returncode, proc.stdout + proc.stderr


class IngestCrosscheckTest(unittest.TestCase):
    def test_dangling_begrip_id_is_fout_exit2(self):
        model = _gs_model([_ot("belastingaanslag", ["b1", "b2"]) | {"id": "ot1"},
                           _ot("iets", ["b9"]) | {"id": "ot2"}])
        code, out = _run_ingest(model, "gegevensspraak", _ingest())
        self.assertEqual(code, 2)
        self.assertIn("begrip-id 'b9'", out)

    def test_dangling_bron_id_is_fout_exit2(self):
        model = _gs_model([_ot("belastingaanslag", ["b1", "b2"], bron_id="br9")])
        code, out = _run_ingest(model, "gegevensspraak", _ingest())
        self.assertEqual(code, 2)
        self.assertIn("bron-id 'br9'", out)

    def test_dangling_regel_id_is_fout_exit2(self):
        regel = _regel("rs1", "Iets", "Regel Iets\n  geldig altijd\n    Een belastingaanslag is invorderbaar.")
        regel["herkomst"] = {"regel_id": "r9", "vindplaatsen": [{"bron_id": "br1", "lid": "1"}]}
        model = _model(regels=[regel], parameters=[], objecttypen=["belastingaanslag"])
        code, out = _run_ingest(model, "regels", _ingest())
        self.assertEqual(code, 2)
        self.assertIn("afleidingsregel-id 'r9'", out)

    def test_ongedekt_begrip_is_waarschuwing_exit1(self):
        # b2 (vervaldatum) wordt nergens aangeraakt → dekking-waarschuwing, geen fout.
        model = _gs_model([_ot("belastingaanslag", ["b1"])])
        code, out = _run_ingest(model, "gegevensspraak", _ingest())
        self.assertEqual(code, 1)
        self.assertIn("Begrip 'b2'", out)
        self.assertIn("door geen enkele declaratie gedekt", out)

    def test_regel_gerefereerd_ongedekt_begrip_krijgt_scherpere_waarschuwing(self):
        # b2 wordt door een afleidingsregel als uitvoer gerefereerd maar niet gedekt →
        # de scherpere melding: de regels-stap kan de begrip-id-koppeling dan niet leggen.
        ingest = _ingest()
        ingest["afleidingsregels"] = [{
            "id": "r1", "naam": "bepalen vervaldatum", "type": "rekenregel",
            "uitvoer": {"begrip_id": "b2"},
            "invoer": [{"begrip_id": "b1"}],
        }]
        model = _gs_model([_ot("belastingaanslag", ["b1"])])
        code, out = _run_ingest(model, "gegevensspraak", ingest)
        self.assertEqual(code, 1)  # waarschuwing, geen blokkade
        self.assertIn("Begrip 'b2'", out)
        self.assertIn("door een afleidingsregel gerefereerd", out)

    def test_happy_path_exit0(self):
        # Beide begrippen gedekt, herkomst geldig, geen waarschuwingen.
        model = _gs_model([
            _ot("belastingaanslag", ["b1"]) | {"id": "ot1"},
            _ot("vervaldatum", ["b2"]) | {"id": "ot2", "datatype": "Datum in dagen"},
        ])
        # zorg dat beide objecttypen een geldig datatype hebben om datatype-waarschuwingen te vermijden
        model["gegevensspraak"]["objecttypen"][0]["attributen"] = []
        model["gegevensspraak"]["objecttypen"][1]["attributen"] = []
        code, out = _run_ingest(model, "gegevensspraak", _ingest())
        self.assertEqual(code, 0, msg=out)

    def test_zonder_ingest_ongewijzigd_gedrag(self):
        # Regressie: model met dangling herkomst maar zónder --ingest → geen ingest-fout.
        model = _gs_model([_ot("iets", ["b9"])])
        model["gegevensspraak"]["objecttypen"][0]["attributen"] = []
        code, out = _run_ingest(model, "gegevensspraak", ingest=None)
        self.assertNotIn("niet in de wetsanalyse", out)
        self.assertIn(code, (0, 1))  # geen blokkerende ingest-fout


if __name__ == "__main__":
    unittest.main()
