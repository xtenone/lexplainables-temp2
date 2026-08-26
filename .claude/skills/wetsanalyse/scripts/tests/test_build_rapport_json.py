"""Tests voor build_rapport_json.py — de rapportbouw uit de gevalideerde werkmap.

Stdlib-only (unittest + subprocess). Draaien:
    python -m unittest discover -s .claude/skills/wetsanalyse/scripts/tests
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "build_rapport_json.py"

ACT2 = {
    "werkgebied": {"naam": "Testwerkgebied"},
    "analysefocus": "test",
    "bronnen": [
        {
            "bron_id": "br1",
            "label": "Wet X art. 1",
            "leden": [{"lid": "1", "tekst": "De belastingplichtige doet aangifte."}],
            "markeringen": [{"id": "m1", "bron_id": "br1", "klasse": "Rechtssubject",
                             "formulering": "De belastingplichtige", "vindplaats": "lid 1"}],
            "verwijzingen": [],
        }
    ],
}

AKKOORD = {"status": "akkoord", "items": {}, "algemeen": ""}


class BuildRapportJsonTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.werk = Path(self._tmp.name) / "werk"
        self.out = Path(self._tmp.name) / "rapport.json"

    def tearDown(self):
        self._tmp.cleanup()

    def _schrijf_ronde(self, activiteit: str, ronde: int, analyse: dict, feedback: dict | None):
        d = self.werk / f"activiteit-{activiteit}" / f"ronde-{ronde}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "analyse.json").write_text(json.dumps(analyse), encoding="utf-8")
        if feedback is not None:
            (d / "feedback.json").write_text(json.dumps(feedback), encoding="utf-8")

    def _run(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--werk", str(self.werk), "--out", str(self.out)],
            text=True, capture_output=True, timeout=30,
        )

    def test_schoon_rapport_exit_0(self):
        self._schrijf_ronde("2", 1, ACT2, AKKOORD)
        res = self._run()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertTrue(self.out.exists())
        self.assertNotIn("geen schoon 'akkoord'", res.stdout)
        rapport = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertEqual(rapport["bronnen"][0]["bron_id"], "br1")
        # Act2-only: begrippen/afleidingsregels blijven leeg.
        self.assertEqual(rapport["begrippen"], [])
        self.assertEqual(rapport["afleidingsregels"], [])
        self.assertNotIn("activiteit3", rapport["reviewlog"])

    def test_ontbrekende_act2_ronde_blokkeert(self):
        # Zonder een activiteit-2-ronde is er niets te bouwen → exit != 0.
        res = self._run()
        self.assertNotEqual(res.returncode, 0)

    def test_geen_schoon_akkoord_waarschuwt_maar_blokkeert_niet(self):
        # Hoogste ronde zonder (schoon) akkoord → waarschuwing in de uitvoer, exit 0.
        self._schrijf_ronde("2", 1, ACT2, {"status": "wijzigingen", "items": {"m1": "x"}, "algemeen": ""})
        res = self._run()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("activiteit 2", res.stdout)
        self.assertIn("geen schoon", res.stdout)


if __name__ == "__main__":
    unittest.main()
