"""Tests voor ingest_rapport.py — de deterministische handoff van wetsanalyse naar regelspraak.

Stdlib-only (unittest + subprocess). Controleert dat de relevante delen uit een
rapport.json worden geëxtraheerd met behoud van de herkomst-id's, dat bronnen worden
getrimd (Brondefinities + via `markering_ids` gerefereerde markeringen blijven; de rest
verdwijnt), en dat dangling referenties (incl. begrip-id's in regelvelden) worden gemeld.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "ingest_rapport.py"

RAPPORT = {
    "werkgebied": {"naam": "Zorgtoeslag", "hoofdvraag": "Wie heeft recht?"},
    "bronnen": [
        {
            "bron_id": "br1",
            "label": "Wzt art. 1",
            "bwbId": "BWBR0018451",
            "artikel": "1",
            "lid": "1",
            "bronreferentie": "jci1.3:c:BWBR0018451&artikel=1&lid=1",
            "versiedatum": "2026-01-01",
            "pad": "Hoofdstuk 1 > Artikel 1",
            "leden": [{"lid": "1", "tekst": "De verzekerde heeft recht op zorgtoeslag."}],
            "markeringen": [
                {"id": "m1", "klasse": "Rechtssubject", "formulering": "De verzekerde"},
                {"id": "m2", "klasse": "Brondefinitie", "formulering": "verzekerde: ..."},
                {"id": "m3", "klasse": "Voorwaarde", "formulering": "indien verzekerd"},
            ],
            "verwijzingen": [
                {"id": "v1", "functie": "definitie", "doel": {"label": "art. 2"}},
            ],
            "samenhang": "n.v.t.",
        }
    ],
    "begrippen": [
        {"id": "b1", "naam": "verzekerde", "klasse": "Rechtssubject",
         "bron_verwijzing": "v1", "markering_ids": ["m1"],
         "vindplaatsen": [{"bron_id": "br1", "lid": "1"}]},
        {"id": "b2", "naam": "recht op zorgtoeslag", "klasse": "Rechtsbetrekking",
         "vindplaatsen": [{"bron_id": "br1", "lid": "1"}]},
    ],
    "afleidingsregels": [
        {"id": "r1", "naam": "bepalen recht op zorgtoeslag", "type": "beslisregel",
         "uitvoer": {"begrip_id": "b2"},
         "invoer": [{"begrip_id": "b1"}],
         "voorwaarden": [{"tekst": "indien verzekerd", "begrip_ids": ["b1"], "verbinding": ""}],
         "vindplaatsen": [{"bron_id": "br1", "lid": "1"}]}
    ],
    "validatiepunten": ["iets"],
    "reviewlog": {"activiteit2": {}, "activiteit3": {}},
}


def _run(rapport: dict) -> tuple[int, str, dict | None]:
    with tempfile.TemporaryDirectory() as d:
        rp = Path(d) / "rapport.json"
        out = Path(d) / "regelspraak" / "werk" / "ingest.json"
        rp.write_text(json.dumps(rapport), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--rapport", str(rp), "--out", str(out)],
            capture_output=True, text=True,
        )
        data = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
        return proc.returncode, proc.stdout, data


class IngestRapportTest(unittest.TestCase):
    def test_extraheert_kerndelen_met_behoud_ids(self):
        code, _out, data = _run(RAPPORT)
        self.assertEqual(code, 0)
        self.assertEqual(data["werkgebied"]["naam"], "Zorgtoeslag")
        self.assertEqual([b["id"] for b in data["begrippen"]], ["b1", "b2"])
        self.assertEqual([r["id"] for r in data["afleidingsregels"]], ["r1"])
        self.assertEqual(data["begrippen"][0]["bron_verwijzing"], "v1")
        self.assertEqual(data["afleidingsregels"][0]["uitvoer"]["begrip_id"], "b2")

    def test_bron_getrimd_brondefinities_plus_gerefereerde_markeringen(self):
        _code, _out, data = _run(RAPPORT)
        bron = data["bronnen"][0]
        # Identificerende velden + leden + verwijzingen blijven; van de markeringen blijven
        # de Brondefinitie ('brondefinities') en de via markering_ids gerefereerde m1
        # ('gekoppelde_markeringen'); de ongerefereerde m3 verdwijnt.
        self.assertEqual(bron["bronreferentie"], "jci1.3:c:BWBR0018451&artikel=1&lid=1")
        self.assertIn("leden", bron)
        self.assertIn("verwijzingen", bron)
        self.assertNotIn("markeringen", bron)
        self.assertEqual([m["id"] for m in bron["brondefinities"]], ["m2"])
        self.assertEqual([m["id"] for m in bron["gekoppelde_markeringen"]], ["m1"])

    def test_dangling_verwijzing_wordt_gemeld(self):
        rapport = json.loads(json.dumps(RAPPORT))
        rapport["begrippen"][0]["bron_verwijzing"] = "v999"
        code, out, _data = _run(rapport)
        self.assertEqual(code, 0)  # melding, geen harde fout
        self.assertIn("v999", out)

    def test_dangling_begrip_id_in_regelveld_wordt_gemeld(self):
        rapport = json.loads(json.dumps(RAPPORT))
        rapport["afleidingsregels"][0]["uitvoer"]["begrip_id"] = "b999"
        code, out, _data = _run(rapport)
        self.assertEqual(code, 0)  # melding, geen harde fout
        self.assertIn("b999", out)
        self.assertIn("uitvoer", out)

    def test_geen_bronnen_blokkeert(self):
        rapport = json.loads(json.dumps(RAPPORT))
        rapport["bronnen"] = []
        code, _out, _data = _run(rapport)
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
