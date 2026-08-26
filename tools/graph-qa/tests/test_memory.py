"""PR 2.4: geheugen-tiers via de LangGraph-checkpointer."""
from __future__ import annotations

import asyncio

from agent.agent import answer_stream, delete_conversation
from fakes import FakeGraph, FakeLLM, make_settings, response, text_block, tool_block

ART_IRI = "urn:bwb:BWBR0004770:artikel:9"


def _run(gen):
    async def collect():
        return [_ async for _ in gen]

    return asyncio.run(collect())


def _turn1_llm():
    return FakeLLM([
        response([tool_block("t1", "get_artikel", {"bwb_id": "BWBR0004770", "artikel": "9"})], "tool_use"),
        response([text_block(f"Artikel 9 IW: zie {ART_IRI}.")], "end_turn"),
    ])


def test_continuiteit_en_pointercontext(tmp_path):
    db = str(tmp_path / "cp.db")
    settings = make_settings(enable_planning=False, checkpoint_db_path=db)

    # Beurt 1: raadpleegt artikel 9 → belandt in messages + entities_seen (durable).
    graph1 = FakeGraph(result=f"<{ART_IRI}> bwb:tekst 'zes weken' .")
    _run(answer_stream("Wat is artikel 9 IW?", "gesprek-1", settings=settings, llm=_turn1_llm(), graph=graph1))

    # Beurt 2: zelfde conversation_id, andere fakes.
    graph2 = FakeGraph(result="")
    llm2 = FakeLLM([response([text_block("Vervolgantwoord.")], "end_turn")])
    _run(answer_stream("En het volgende lid daarvan?", "gesprek-1", settings=settings, llm=llm2, graph=graph2))

    agent_call = llm2.calls[0]
    # Episodisch: de eerdere user-vraag zit in de doorgegeven messages.
    serialized = str(agent_call["messages"])
    assert "Wat is artikel 9 IW?" in serialized
    # Semantisch/entiteit: eerder geraadpleegde IRI als pointer-context in de system-prompt.
    assert ART_IRI in agent_call["system"]
    assert "GESPREKSCONTEXT" in agent_call["system"]


def test_nieuw_gesprek_start_leeg(tmp_path):
    settings = make_settings(enable_planning=False, checkpoint_db_path=str(tmp_path / "cp.db"))
    graph = FakeGraph(result="")
    llm = FakeLLM([response([text_block("Antwoord.")], "end_turn")])
    _run(answer_stream("Losse vraag.", "vers-gesprek", settings=settings, llm=llm, graph=graph))
    msgs = llm.calls[0]["messages"]
    # Alleen de nieuwe user-vraag; geen eerdere historie.
    assert len(msgs) == 1 and msgs[0]["role"] == "user"


def test_delete_conversation_wist_de_thread(tmp_path):
    """Na delete_conversation start dezelfde conversation_id met een LEGE historie (privacy)."""
    db = str(tmp_path / "cp.db")
    settings = make_settings(enable_planning=False, checkpoint_db_path=db)

    graph1 = FakeGraph(result=f"<{ART_IRI}> bwb:tekst 'zes weken' .")
    _run(answer_stream("Wat is artikel 9 IW?", "weg-1", settings=settings, llm=_turn1_llm(), graph=graph1))

    import asyncio
    asyncio.run(delete_conversation("weg-1", settings=settings))

    # Volgende beurt op diezelfde id: alleen de nieuwe user-vraag, geen eerdere historie.
    llm2 = FakeLLM([response([text_block("Vers.")], "end_turn")])
    _run(answer_stream("Nieuwe vraag.", "weg-1", settings=settings, llm=llm2, graph=FakeGraph(result="")))
    msgs = llm2.calls[0]["messages"]
    assert len(msgs) == 1 and msgs[0]["role"] == "user"


def test_delete_onbekende_conversation_is_idempotent(tmp_path):
    """Een onbekende id wissen is geen fout (idempotent)."""
    import asyncio
    settings = make_settings(enable_planning=False, checkpoint_db_path=str(tmp_path / "cp.db"))
    asyncio.run(delete_conversation("bestaat-niet", settings=settings))


def test_zonder_memory_context_geen_injectie(tmp_path):
    db = str(tmp_path / "cp.db")
    base = dict(enable_planning=False, checkpoint_db_path=db, enable_memory_context=False)
    graph1 = FakeGraph(result=f"<{ART_IRI}> bwb:tekst 'x' .")
    _run(answer_stream("q1", "g", settings=make_settings(**base), llm=_turn1_llm(), graph=graph1))

    llm2 = FakeLLM([response([text_block("q2-antwoord.")], "end_turn")])
    _run(answer_stream("q2", "g", settings=make_settings(**base), llm=llm2, graph=FakeGraph(result="")))
    assert "GESPREKSCONTEXT" not in llm2.calls[0]["system"]
