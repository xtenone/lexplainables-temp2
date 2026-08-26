"""WP-A + WP-C + WP-D: de loop draait op fakes via de getypeerde toollaag."""
from __future__ import annotations

import asyncio

from agent.agent import answer_stream
from fakes import FakeGraph, FakeLLM, make_settings, response, text_block, tool_block

ART_IRI = "urn:bwb:BWBR0004770:artikel:9"


def _run(gen):
    async def collect():
        return [ev async for ev in gen]

    return asyncio.run(collect())


def _make():
    # planning uit: test de kern-loop (agent↔tools→verify) zonder extra plan-call. Correctie ook uit:
    # het eindantwoord hieronder is met opzet ongegrond (een verzonnen BWB-id) omdat dat de trace en
    # de bronnen aantoonbaar maakt — niet omdat deze test over de correctieronde gaat. Met correctie
    # aan zou elke test hier een extra modelantwoord moeten meebrengen dat niets toevoegt.
    settings = make_settings(enable_planning=False, grounding_correct=False)
    graph = FakeGraph(result=f"<{ART_IRI}> bwb:citeertitel \"Invorderingswet 1990\" .")
    llm = FakeLLM([
        # Het model kiest een GETYPEERDE tool, geen rauwe SPARQL.
        response(
            [text_block("Ik zoek de regelingen op."),
             tool_block("t1", "list_regelingen", {})],
            "tool_use",
        ),
        # Eindantwoord met een VERZONNEN citatie die nooit uit de graaf kwam.
        response([text_block("Zie de Invorderingswet 1990. (verzonnen: BWBR9999999)")], "end_turn"),
    ])
    return settings, graph, llm


def test_loop_draait_via_getypeerde_tool():
    settings, graph, llm = _make()
    events = _run(answer_stream("vraag", settings=settings, llm=llm, graph=graph))
    assert "done" in [e["type"] for e in events]
    assert graph.closed is True
    assert graph.queries  # er is een SPARQL-query uitgevoerd
    # De uitgevoerde query is die van list_regelingen (eigen-IRI-ruimtefilter).
    assert any("bwb:Regeling" in q and "STRSTARTS" in q for q in graph.queries)


def test_bronnen_uit_tooltrace_niet_uit_modeltekst():
    settings, graph, llm = _make()
    events = _run(answer_stream("vraag", settings=settings, llm=llm, graph=graph))
    sources = next(e for e in events if e["type"] == "sources")["sources"]
    uris = [s["uri"] for s in sources]
    assert ART_IRI in uris  # echte vindplaats uit de tool-output
    assert not any("BWBR9999999" in u for u in uris)  # verzinsel uit de tekst niet


def test_geen_repository_id_meer_in_toolargs():
    # De domeintools kennen de repo zelf; het model krijgt geen repositoryId-veld.
    from agent.tools import anthropic_schemas

    for tool in anthropic_schemas():
        assert "repositoryId" not in tool["input_schema"].get("properties", {})


def test_eindtekst_streamt_verbatim():
    # De token-stream reproduceert de antwoordtekst (incl. newlines) letterlijk.
    settings = make_settings(enable_planning=False)
    graph = FakeGraph(result=ART_IRI)
    llm = FakeLLM([
        response([text_block("Regel een.\n\nRegel twee.")], "end_turn"),
    ])
    events = _run(answer_stream("vraag", settings=settings, llm=llm, graph=graph))
    text = "".join(e["content"] for e in events if e["type"] == "token")
    assert text == "Regel een.\n\nRegel twee."


def test_agentfout_lekt_geen_interne_details():
    """Een mislukte beurt levert een gesaniteerde melding, geen ruwe exception.

    De ruwe fout van een LLM- of MCP-aanroep bevat request-details (endpoints, payload-fragmenten).
    Die horen in het server-log, niet in de browser — de api saniteert de modelprovider-test om
    dezelfde reden.
    """
    import asyncio

    from agent.agent import answer_stream
    from fakes import FakeGraph, make_settings

    class KapotteLLM:
        def stream(self, **kw):  # noqa: ANN003
            raise RuntimeError("connect naar https://intern.example/v1/messages mislukt: key=abc123")

        def create(self, **kw):  # noqa: ANN003
            raise RuntimeError("connect naar https://intern.example/v1/messages mislukt: key=abc123")

    async def verzamel():
        return [e async for e in answer_stream(
            "vraag", settings=make_settings(enable_planning=False), llm=KapotteLLM(), graph=FakeGraph(result="")
        )]

    events = _run_events(verzamel)
    fouten = [e for e in events if e.get("type") == "error"]
    assert fouten, "een mislukte beurt moet een error-event opleveren"
    bericht = fouten[0]["message"]
    assert "intern.example" not in bericht
    assert "abc123" not in bericht
    assert "server-log" in bericht


def _run_events(coro_fn):
    import asyncio

    return asyncio.run(coro_fn())


def test_stoppen_haalt_de_graaf_van_een_nodegrens():
    """Coöperatief stoppen: de vlag gaat om, de graaf betreedt geen nieuwe node meer.

    Bewust geen taak-annulering. De nodes zijn synchroon en de MCP-verbinding wordt in een `finally`
    gesloten — die onder een draaiende executor-thread wegtrekken breekt hem. Wat je hier ziet is de
    prijs én de winst: er komt geen extra LLM-call meer, de graaf sluit netjes af (`graph.closed`),
    en de stroom eindigt met een gewone `done` in plaats van een fout.
    """
    settings, graph, llm = _make()
    events = _run(answer_stream("vraag", settings=settings, llm=llm, graph=graph,
                                stop_check=lambda: True))

    assert [e["type"] for e in events] == ["done"]  # geen enkele node is uitgevoerd
    assert graph.closed is True
    assert llm.calls == []  # er is geen model aangeroepen, dus ook niets betaald


def test_zonder_stopverzoek_verandert_er_niets():
    """De bewaking mag de gewone lus niet raken."""
    settings, graph, llm = _make()
    events = _run(answer_stream("vraag", settings=settings, llm=llm, graph=graph,
                                stop_check=lambda: False))
    assert "done" in [e["type"] for e in events]
    assert llm.calls
