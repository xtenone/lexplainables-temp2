"""Fase 3 PR 3.1: supervisor routeert naar een specialist met eigen tool-subset."""
from __future__ import annotations

import asyncio

from agent.agent import answer_stream
from fakes import FakeGraph, FakeLLM, make_settings, response, text_block


def _run(gen):
    async def collect():
        return [ev async for ev in gen]

    return asyncio.run(collect())


def _route_to(specialist: str) -> FakeLLM:
    return FakeLLM([
        response([text_block(f"SPECIALIST: {specialist}\nPLAN: kort plan.")], "end_turn"),  # router
        response([text_block("Direct antwoord.")], "end_turn"),                              # agent (geen tools)
    ])


def _agent_tools(llm: FakeLLM) -> set[str]:
    # llm.calls[0] = router (create), [1] = agent (stream) → de tool-set die de agent zag.
    return {t["name"] for t in llm.calls[1]["tools"]}


def test_duiding_beperkt_toolset():
    llm = _route_to("duiding")
    events = _run(answer_stream("Hoe hangt art. 9 samen met art. 27?", settings=make_settings(),
                                llm=llm, graph=FakeGraph(result="")))
    names = _agent_tools(llm)
    assert "get_context" in names and "referenced_by" in names
    assert "resolve_begrip" not in names  # definitie-only tool
    assert any(e["type"] == "status" and "duiding" in e["message"] for e in events)


def test_definitie_beperkt_toolset():
    llm = _route_to("definitie")
    _run(answer_stream("Wat betekent invordering?", settings=make_settings(), llm=llm, graph=FakeGraph(result="")))
    names = _agent_tools(llm)
    assert "resolve_begrip" in names
    assert "get_context" not in names  # duiding-only tool


def test_definitie_prompt_wijst_naar_artikel_1_en_2_en_de_onderdelen():
    """Twee terugkerende omwegen die de prompt nu afsnijdt.

    De agent probeerde eerst artikel 1, vond daar niets en ging pas daarna naar artikel 2 — een
    extra ronde per definitievraag. En hij citeerde de vindplaats van het lid terwijl hij een
    onderdeel aanhaalde, waardoor de verwijzing op 25 definities uitkwam in plaats van op één.
    """
    from agent.specialists import SPECIALISTS

    prompt = SPECIALISTS["definitie"].system
    assert "artikel 1 of 2" in prompt
    assert "in één beurt" in prompt
    assert "&o=k" in prompt, "de vindplaats van het onderdeel, niet die van het lid"


def test_onbekende_route_valt_terug_op_algemeen():
    llm = FakeLLM([
        response([text_block("SPECIALIST: onzin\nPLAN: iets.")], "end_turn"),
        response([text_block("Antwoord.")], "end_turn"),
    ])
    _run(answer_stream("vraag", settings=make_settings(), llm=llm, graph=FakeGraph(result="")))
    assert len(_agent_tools(llm)) == 13  # alle tools


def test_planning_uit_is_algemeen_alle_tools():
    llm = FakeLLM([response([text_block("Antwoord.")], "end_turn")])
    _run(answer_stream("vraag", settings=make_settings(enable_planning=False),
                       llm=llm, graph=FakeGraph(result="")))
    # geen router → llm.calls[0] is de agent-stream-call
    assert len({t["name"] for t in llm.calls[0]["tools"]}) == 13
