"""Annoteren op ONDERWERP in plaats van op bepaling.

"Annoteer alles over aansprakelijkheid van de bestuurder" wijst geen bepaling aan. De ophaal-agent
zoekt er dan in de graaf naar en legt kandidaten voor; de jurist kiest. Het alternatief — de agent
laten gokken welke bepaling bedoeld is — levert een annotatie op een bepaling die niemand vroeg.
"""
from __future__ import annotations

import asyncio
import json

from agent.agent import answer_stream
from agent.orchestrator import _kandidaten_uit_json
from fakes import FakeGraph, FakeLLM, make_settings, response, text_block, tool_block

ZOEK_TSV = json.dumps('?iri\t?titel\n"iri"\t"Invorderingswet 1990"')

KANDIDATEN_JSON = json.dumps({"kandidaten": [
    {"bwbId": "BWBR0004770", "artikel": "36", "lid": "", "citeertitel": "Invorderingswet 1990",
     "fragment": "Hoofdelijk aansprakelijk is voor de loonbelasting…"},
    {"bwbId": "BWBR0004770", "artikel": "36a", "lid": "1", "citeertitel": "Invorderingswet 1990",
     "fragment": "Hoofdelijk aansprakelijk is de bestuurder…"},
]})


def _run(gen):
    async def collect():
        return [ev async for ev in gen]

    return asyncio.run(collect())


# --- de parser ------------------------------------------------------------------------------------

def test_parser_ontdubbelt_en_begrenst():
    tekst = json.dumps({"kandidaten": [
        {"bwbId": "BWBR1", "artikel": "1"},
        {"bwbId": "BWBR1", "artikel": "1"},          # zelfde bepaling
        {"bwbId": "BWBR1", "artikel": "1", "lid": "2"},
        *[{"bwbId": "BWBR1", "artikel": str(n)} for n in range(10, 30)],
    ]})
    uit = _kandidaten_uit_json(tekst)
    assert len(uit) == 8, "hoogstens 8, anders is het geen keuze meer maar een lijst"
    assert (uit[0]["artikel"], uit[1]["lid"]) == ("1", "2")


def test_parser_negeert_onvolledige_kandidaten():
    """Zonder bwbId + artikel is een kandidaat niet aanklikbaar — dan liever weglaten."""
    tekst = json.dumps({"kandidaten": [
        {"artikel": "36"}, {"bwbId": "BWBR1"}, "onzin", {"bwbId": "BWBR1", "artikel": "36"},
    ]})
    assert [k["artikel"] for k in _kandidaten_uit_json(tekst)] == ["36"]


def test_parser_laat_een_gewoon_doel_met_rust():
    """Een doel-JSON mag hier nooit als kandidaat doorgaan; anders slaat elke annotatie om in een keuze."""
    assert _kandidaten_uit_json('{"bwbId":"BWBR0004770","artikel":"9","lid":"1"}') == []


# --- de keten -------------------------------------------------------------------------------------

def _onderwerp_scenario(*, decompositie: bool = True):
    llm = FakeLLM([
        response([text_block("WORKERS: annotatie\nPLAN: zoek de bepalingen over dit onderwerp")], "end_turn"),
        response([tool_block("t1", "semantic_search", {"query": "aansprakelijkheid bestuurder"})], "tool_use"),
        response([text_block(KANDIDATEN_JSON)], "end_turn"),
    ])
    events = _run(answer_stream(
        "annoteer alles over aansprakelijkheid van de bestuurder",
        settings=make_settings(enable_decomposition=decompositie), llm=llm, graph=FakeGraph(result=ZOEK_TSV),
    ))
    return events, llm


def test_onderwerp_levert_kandidaten_en_annoteert_nog_niets():
    events, llm = _onderwerp_scenario()

    kandidaten = next(e for e in events if e["type"] == "kandidaten")["kandidaten"]
    assert [k["artikel"] for k in kandidaten] == ["36", "36a"]

    soorten = {e["type"] for e in events}
    assert "element" not in soorten and "doel" not in soorten, "de jurist kiest eerst"
    assert llm.index == 3, "geen annoteer- en geen critic-call"


def test_de_gebruiker_hoort_wat_er_te_kiezen_valt():
    """Zonder tekst in de thread ziet de jurist alleen een paneel opengaan zonder uitleg."""
    events, _ = _onderwerp_scenario()
    tekst = "".join(e["content"] for e in events if e["type"] == "token")
    assert "2 bepalingen" in tekst


def test_werkt_ook_zonder_decompositie():
    """build_graph bedraadt de annotatieroute twee keer; dev draait met ENABLE_DECOMPOSITION=0."""
    events, _ = _onderwerp_scenario(decompositie=False)
    assert next(e for e in events if e["type"] == "kandidaten")["kandidaten"]
