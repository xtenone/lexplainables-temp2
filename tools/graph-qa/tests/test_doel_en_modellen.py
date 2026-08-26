"""Twee knoppen die de annotatieketen goedkoper én betrouwbaarder maken.

1. **Model per rol** — de router en de ophaal-agent mogen op een ander model draaien dan de
   annoteerder en de Critic. Die laatste twee vellen het juridische oordeel en houden daarom geen
   eigen knop: er is geen env-var waarmee je ze per ongeluk degradeert.
2. **Een meegegeven `doel`** — weet de werkplek de bepaling al, dan slaat de beurt de supervisor én
   de ophaal-agent over. Dat scheelt calls, maar de echte winst is dat de agent dan niet meer bij
   een ándere bepaling kan uitkomen dan de jurist aanwees.
"""
from __future__ import annotations

import asyncio
import json

from agent.agent import answer_stream
from agent.config import Settings
from fakes import FakeGraph, FakeLLM, make_settings, response, text_block, tool_block

#: Antwoord op `get_lid` — wat de ophaal-agent als tool-resultaat terugkrijgt.
LID_TSV = json.dumps(
    '?nummer\t?tekst\t?jci\n"1"\t"De ontvanger verleent uitstel van betaling indien de schuldenaar '
    'daarom verzoekt."@nl\t"jci"'
)

#: Antwoord op `get_artikel` — de vorm die `artikel_corpus` leest bij het GERICHT ophalen. Zonder
#: ophaal-agent is er geen tool-trace om op terug te vallen, dus loopt het corpus hier langs.
ARTIKEL_TSV = json.dumps(
    "?tekst\t?jci\t?lid\t?lidnummer\t?lidtekst\t?onderdeel\t?onderdeeltekst\n"
    '\t"jci"\t"lid-1"\t"1"\t"De ontvanger verleent uitstel van betaling indien de schuldenaar '
    'daarom verzoekt."@nl\t\t'
)

VRAAG = "annoteer artikel 9 lid 1 van de Invorderingswet 1990"
DOEL = {"bwbId": "BWBR0004770", "artikel": "9", "lid": "1", "citeertitel": "Invorderingswet 1990"}


def _run(gen):
    async def collect():
        return [ev async for ev in gen]

    return asyncio.run(collect())


def _annoteer(elementen: list[dict]):
    return response([text_block(json.dumps({"elementen": elementen}))], "end_turn")


def _critic(oordelen: list[dict]):
    return response([text_block(json.dumps({"oordelen": oordelen, "ontbrekend": []}))], "end_turn")


_ELEMENT = {"id": "el-a", "klasse": "Rechtssubject", "tekst": "De ontvanger", "lid": "1"}
_GROEN = {"id": "el-a", "aandacht": "groen", "motivatie": "juist"}


def _aanloop() -> list:
    """Supervisor + de twee ophaal-beurten — de weg zonder meegegeven doel."""
    return [
        response([text_block("WORKERS: annotatie\nPLAN: annoteer art 9 lid 1")], "end_turn"),
        response([tool_block("t1", "get_lid", {"bwb_id": "BWBR0004770", "artikel": "9", "lid": "1"})],
                 "tool_use"),
        response([text_block('{"bwbId":"BWBR0004770","artikel":"9","lid":"1"}')], "end_turn"),
    ]


# --- 1. model per rol -----------------------------------------------------------------------------

def test_model_voor_valt_terug_op_het_hoofdmodel():
    s = Settings(llm_model="sterk")
    assert s.model_voor("router") == "sterk"
    assert s.model_voor("ophaal") == "sterk"
    # De annoteerder en de Critic hebben géén eigen knop: dat is de grens, geen omissie.
    assert s.model_voor("annoteerder") == "sterk"
    assert s.model_voor("critic") == "sterk"
    assert s.model_voor("bestaat-niet") == "sterk"


def test_model_voor_gebruikt_de_rol_override():
    s = Settings(llm_model="sterk", llm_model_router="klein", llm_model_ophaal="middel")
    assert s.model_voor("router") == "klein"
    assert s.model_voor("ophaal") == "middel"
    assert s.model_voor("annoteerder") == "sterk"


def test_from_env_leest_de_rol_modellen():
    s = Settings.from_env({"LLM_MODEL": "sterk", "LLM_MODEL_ROUTER": "klein"})
    assert (s.model_voor("router"), s.model_voor("ophaal")) == ("klein", "sterk")


def test_elke_rol_draait_op_zijn_eigen_model():
    """De volgorde van de calls is de volgorde van de keten: router → ophaal ×2 → annoteer → critic."""
    llm = FakeLLM([*_aanloop(), _annoteer([_ELEMENT]), _critic([_GROEN])])
    _run(answer_stream(
        VRAAG,
        settings=make_settings(llm_model="sterk", llm_model_router="klein", llm_model_ophaal="middel"),
        llm=llm, graph=FakeGraph(result=LID_TSV),
    ))

    modellen = [c["model"] for c in llm.calls]
    assert modellen == ["klein", "middel", "middel", "sterk", "sterk"]


def test_zonder_overrides_draait_alles_op_een_model():
    """Terugdraaien is een lege env-var: dan is de keten byte-voor-byte de oude."""
    llm = FakeLLM([*_aanloop(), _annoteer([_ELEMENT]), _critic([_GROEN])])
    _run(answer_stream(
        VRAAG, settings=make_settings(llm_model="sterk"), llm=llm, graph=FakeGraph(result=LID_TSV),
    ))
    assert {c["model"] for c in llm.calls} == {"sterk"}


# --- 2. een meegegeven doel -----------------------------------------------------------------------

def _met_doel(doel: dict, llm: FakeLLM):
    return _run(answer_stream(
        VRAAG, doel=doel, settings=make_settings(), llm=llm, graph=FakeGraph(result=ARTIKEL_TSV),
    ))


def test_een_meegegeven_doel_slaat_supervisor_en_ophaal_over():
    """Twee LLM-calls in plaats van vijf: alleen nog annoteren en beoordelen."""
    llm = FakeLLM([_annoteer([_ELEMENT]), _critic([_GROEN])])
    events = _met_doel(DOEL, llm)

    assert len(llm.calls) == 2, "supervisor en ophaal-agent horen niet te draaien"
    elementen = [e["element"] for e in events if e["type"] == "element"]
    assert [el["klasse"] for el in elementen] == ["Rechtssubject"]


def test_het_meegegeven_doel_is_het_doel_dat_eruit_komt():
    """De bepaling die de jurist aanwees, niet een die een agent erbij zocht."""
    llm = FakeLLM([_annoteer([_ELEMENT]), _critic([_GROEN])])
    events = _met_doel(DOEL, llm)

    doel_ev = next(e["doel"] for e in events if e["type"] == "doel")
    assert doel_ev["bwbId"] == "BWBR0004770"
    assert (doel_ev["artikel"], doel_ev["lid"]) == ("9", "1")
    assert doel_ev["citeertitel"] == "Invorderingswet 1990"


def test_het_corpus_komt_gericht_uit_de_graaf():
    """Zonder ophaal-agent is er geen tool-trace; het corpus moet dus uit de gerichte SPARQL komen."""
    graaf = FakeGraph(result=ARTIKEL_TSV)
    llm = FakeLLM([_annoteer([_ELEMENT]), _critic([_GROEN])])
    _run(answer_stream(VRAAG, doel=DOEL, settings=make_settings(), llm=llm, graph=graaf))

    assert graaf.queries, "er hoort één gerichte ophaalactie te zijn gedaan"
    assert "De ontvanger" in llm.calls[0]["system"] or "De ontvanger" in str(llm.calls[0]["messages"])


def test_een_half_doel_gaat_gewoon_de_gewone_weg():
    """Alleen een bwbId is geen bepaling: dan is er wél iets te zoeken."""
    llm = FakeLLM([*_aanloop(), _annoteer([_ELEMENT]), _critic([_GROEN])])
    _run(answer_stream(
        VRAAG, doel={"bwbId": "BWBR0004770"}, settings=make_settings(),
        llm=llm, graph=FakeGraph(result=LID_TSV),
    ))
    assert len(llm.calls) == 5


def test_zonder_doel_verandert_er_niets():
    llm = FakeLLM([*_aanloop(), _annoteer([_ELEMENT]), _critic([_GROEN])])
    events = _run(answer_stream(
        VRAAG, settings=make_settings(), llm=llm, graph=FakeGraph(result=LID_TSV),
    ))
    assert len(llm.calls) == 5
    assert [e["element"]["id"] for e in events if e["type"] == "element"] == ["el-a"]
