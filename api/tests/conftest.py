"""Test-fixtures + fakes voor LLM en MCP, zodat de hele engine zonder netwerk draait."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.llm.base import LLMResult  # noqa: E402

_LID_RE = re.compile(r"^Lid (\S+): (.*)$", re.MULTILINE)

ARTIKEL_DATA = {
    "citeertitel": "Testwet",
    "versiedatum": "2026-01-01",
    "bwbId": "BWBR9999999",
    "artikel": "1",
    "pad": "Hoofdstuk 1 > Artikel 1",
    "bronreferentie": "jci1.3:c:BWBR9999999&artikel=1",
    "leden": [{
        "lid": "1",
        "tekst": "De belastingplichtige dient aangifte te doen.",
        "bronreferentie": "jci1.3:c:BWBR9999999&artikel=1&lid=1&g=2026-01-01",
        "verwijzingen": [{
            "soort": "extref", "target": "jci1.3:c:BWBR0000001&artikel=2",
            "label": "artikel 2 van de Testdefinitiewet", "bwbIdDoel": "BWBR0000001", "extern": True,
        }],
    }],
}


class FakeWettenbank:
    def __init__(self, data: dict | None = None, fout: Exception | None = None) -> None:
        self.data = data or ARTIKEL_DATA
        self.fout = fout

    async def artikel(self, bwb_id: str, artikel: str, lid: str | None = None) -> dict:
        if self.fout:
            raise self.fout
        return self.data


class FakeLLM:
    """Produceert brongetrouwe output: citeert letterlijk de eerste lid-tekst uit de prompt."""

    def __init__(self, hallucineer: bool = False) -> None:
        self.hallucineer = hallucineer
        self.calls = 0

    async def complete(self, system: str, user: str, schema=None) -> LLMResult:
        self.calls += 1
        m = _LID_RE.search(user)
        lidnr, tekst = (m.group(1), m.group(2)) if m else ("1", "")
        citaat = "VERZONNEN TEKST DIE NIET IN DE WET STAAT" if self.hallucineer else tekst
        is_inventaris = "OPDRACHT (stap 1b" in user
        is_act3a = "OPDRACHT (activiteit 3a" in user          # stap 3a — begrippen
        is_act3b = "OPDRACHT (activiteit 3b" in user          # stap 3b — regels
        is_act3_revise = "HERZIENE werkgebied-brede begrippenlijst" in user
        is_revise_act2 = "per bron de HERZIENE" in user
        heeft_begrippenlijst = "AANGELEVERDE BESTAANDE BEGRIPPENLIJST" in user
        # RegelSpraak-vervolgfase (vers én revise) — eigen opdracht-markers.
        is_rs_gegevens = "OPDRACHT (GegevensSpraak)" in user or "HERZIENE GegevensSpraak" in user
        is_rs_regels = "OPDRACHT (RegelSpraak-regels)" in user or "HERZIENE RegelSpraak-regels" in user

        if is_rs_gegevens:
            data = {
                "objecttypen": [{
                    "id": "ot1", "naam": "belastingplichtige", "lidwoord": "de",
                    "meervoud": "belastingplichtigen", "bezield": True,
                    "attributen": [], "kenmerken": [],
                    "regelspraak_tekst": "Objecttype de belastingplichtige (bezield)",
                    "herkomst": {"begrip_ids": ["b1"], "vindplaatsen": [{"bron_id": "br1", "lid": "1"}]},
                }],
                "parameters": [], "feittypen": [], "domeinen": [], "eenheidssystemen": [],
                "dimensies": [], "tijdlijnen": [], "dagsoorten": [],
            }
            return LLMResult(data=data, model="fake-model", provider="fake",
                             output_strategie="prompt_and_parse")
        if is_rs_regels:
            data = {
                "regels": [{
                    "id": "rs1", "naam": "Beslis aangifteplicht", "soort": "kenmerktoekenning",
                    "regelspraak_tekst": "Regel Beslis aangifteplicht\n  geldig altijd\n"
                                         "    Een belastingplichtige is aangifteplichtig.",
                    "herkomst": {"regel_id": "r1", "vindplaatsen": [{"bron_id": "br1", "lid": "1"}]},
                }],
                "validatiepunten": ["Open norm: 'aangifte' niet gedefinieerd."],
            }
            return LLMResult(data=data, model="fake-model", provider="fake",
                             output_strategie="prompt_and_parse")

        markeringen = [{"id": "m1", "formulering": citaat, "klasse": "Rechtssubject",
                        "vindplaats": f"lid {lidnr}", "toelichting": "drager van de plicht"}]
        verwijzingen = [{
            "id": "v1", "bron_lid": f"lid {lidnr}", "soort": "extref", "functie": "definitie",
            "doel": {"label": "artikel 2 van de Testdefinitiewet",
                     "target": "jci1.3:c:BWBR0000001&artikel=2", "bwbId": "BWBR0000001"},
            "status": "opgehaald", "betekenis": "Definieert de belastingplichtige.",
        }]

        if is_inventaris:
            # Fase 2a (per bron): één te-volgen definitie-verwijzing met een resolvebaar target.
            data = {"verwijzingen": [{
                "id": "v1", "bron_lid": f"lid {lidnr}", "soort": "extref", "functie": "definitie",
                "doel": {"label": "artikel 2 van de Testdefinitiewet",
                         "target": "jci1.3:c:BWBR0000001&artikel=2", "bwbId": "BWBR0000001"},
                "volgen": True,
            }]}
        elif is_act3a:
            # Stap 3a — alleen de werkgebied-brede begrippen (nieuw act-3-schema).
            begrip = {
                "id": "b1", "naam": "belastingplichtige", "klasse": "Rechtssubject",
                "definitie": "degene die aangifte moet doen", "is_interpretatie": True,
                "markering_ids": ["m1"],
                "vindplaatsen": [{"bron_id": "br1", "lid": lidnr}],
            }
            if heeft_begrippenlijst:
                begrip["herkomst"] = {"status": "hergebruikt", "aangeleverd_id": "ab1"}
            data = {
                "begrippen": [begrip],
                "validatiepunten": ["Open norm: 'aangifte' niet gedefinieerd in dit artikel."],
            }
        elif is_act3b:
            # Stap 3b — regels op begrip-id's; de uitvoer ontbreekt in 3a en komt als
            # nieuw begrip mee (test het doornummer/remap-pad in de merge).
            data = {
                "afleidingsregels": [{
                    "id": "r1", "naam": "bepalen aangifteplicht", "type": "beslisregel",
                    "uitvoer": {"begrip_id": "nb1"},
                    "invoer": [{"begrip_id": "b1", "toelichting": "drager van de plicht"}],
                    "voorwaarden": [{"tekst": "indien belastingplichtig",
                                     "begrip_ids": ["b1"], "verbinding": ""}],
                    "markering_ids": ["m1"],
                    "vindplaatsen": [{"bron_id": "br1", "lid": lidnr}],
                }],
                "nieuwe_begrippen": [{
                    "id": "nb1", "naam": "aangifteplicht", "klasse": "Rechtsbetrekking",
                    "definitie": "de plicht om aangifte te doen", "is_interpretatie": True,
                    "verwijst_naar_begrippen": ["b1"], "markering_ids": ["m1"],
                    "vindplaatsen": [{"bron_id": "br1", "lid": lidnr}],
                }],
                "validatiepunten": [],
            }
        elif is_act3_revise:
            # Revise act-3: begrippen + regels in één herziene levering (nieuw schema).
            data = {
                "begrippen": [
                    {"id": "b1", "naam": "belastingplichtige", "klasse": "Rechtssubject",
                     "definitie": "degene die aangifte moet doen", "is_interpretatie": True,
                     "markering_ids": ["m1"],
                     "vindplaatsen": [{"bron_id": "br1", "lid": lidnr}]},
                    {"id": "b2", "naam": "aangifteplicht", "klasse": "Rechtsbetrekking",
                     "definitie": "de plicht om aangifte te doen", "is_interpretatie": True,
                     "verwijst_naar_begrippen": ["b1"], "markering_ids": ["m1"],
                     "vindplaatsen": [{"bron_id": "br1", "lid": lidnr}]},
                ],
                "afleidingsregels": [{
                    "id": "r1", "naam": "bepalen aangifteplicht", "type": "beslisregel",
                    "uitvoer": {"begrip_id": "b2"},
                    "invoer": [{"begrip_id": "b1", "toelichting": "drager van de plicht"}],
                    "voorwaarden": [{"tekst": "indien belastingplichtig",
                                     "begrip_ids": ["b1"], "verbinding": ""}],
                    "markering_ids": ["m1"],
                    "vindplaatsen": [{"bron_id": "br1", "lid": lidnr}],
                }],
                "validatiepunten": ["Open norm: 'aangifte' niet gedefinieerd in dit artikel."],
            }
        elif is_revise_act2:
            # Revise act-2: per bron de herziene markeringen/verwijzingen (werkgebied-vorm).
            data = {"bronnen": [{
                "bron_id": "br1", "reikwijdte": "lid 1", "geraadpleegde": "",
                "markeringen": markeringen, "verwijzingen": verwijzingen,
                "samenhang": "De belastingplichtige is plichthebbende.",
            }]}
        else:
            # Verse act-2 per bron: het LLM levert per bron de platte markeringen/verwijzingen.
            data = {
                "markeringen": markeringen, "verwijzingen": verwijzingen,
                "samenhang": "De belastingplichtige is plichthebbende.",
                "type": "wet", "reikwijdte": "lid 1", "geraadpleegde": "",
            }
        return LLMResult(data=data, model="fake-model", provider="fake", output_strategie="prompt_and_parse")


@pytest.fixture
def settings(tmp_path) -> Settings:
    s = Settings()
    s.analyses_dir = tmp_path / "analyses"
    s.analyses_dir.mkdir(parents=True, exist_ok=True)
    s.max_autocorrectie = 0
    s.max_rondes = 6
    s.transient_max_retries = 0  # geen backoff-slaap in tests
    return s


@pytest.fixture
async def store(settings):
    from app import db
    from app.postgres_store import PostgresStore

    # In-memory SQLite (StaticPool → één gedeelde DB) met portable SQL — zelfde codepad als Postgres.
    db.init_engine("sqlite+aiosqlite://")
    await db.create_all()
    try:
        yield PostgresStore(settings)
    finally:
        await db.dispose_engine()


@pytest.fixture
async def engine(settings, store):
    from app.engine.orchestrator import WetsanalyseEngine
    return WetsanalyseEngine(settings, store, FakeLLM(), FakeWettenbank())
