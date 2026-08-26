"""PR 2.3: LangGraph-orkestrator — plan→retrieve→reason→verify + streaming."""
from __future__ import annotations

import asyncio

from agent.agent import answer_stream
from fakes import FakeGraph, FakeLLM, make_settings, response, text_block, tool_block

ART_IRI = "urn:bwb:BWBR0004770:artikel:9"


def _run(gen):
    async def collect():
        return [ev async for ev in gen]

    return asyncio.run(collect())


def test_volledige_stroom_plan_tools_verify_finalize():
    settings = make_settings()  # planning AAN
    graph = FakeGraph(result=f"<{ART_IRI}> bwb:tekst 'zes weken' .")
    llm = FakeLLM([
        response([text_block("Aanpak: get_artikel 9 IW.")], "end_turn"),                      # plan (create)
        response([tool_block("t1", "get_artikel", {"bwb_id": "BWBR0004770", "artikel": "9"})], "tool_use"),
        response([text_block(f"Artikel 9 IW ({ART_IRI}): zes weken.")], "end_turn"),           # eindantwoord
    ])
    events = _run(answer_stream("vraag", settings=settings, llm=llm, graph=graph))
    types = [e["type"] for e in events]

    assert types[0] == "status" and "Aanpak" in events[0]["message"]          # plan-node eerst
    assert any(e["type"] == "status" and "Graaf bevragen" in e["message"] for e in events)  # tools-node
    assert graph.queries                                                       # tool echt uitgevoerd
    # volgorde aan het eind: sources → grounding → done
    assert types.index("sources") < types.index("grounding") < types.index("done")
    # tokens gestreamd
    assert any(e["type"] == "token" for e in events)


def test_bronnen_uit_tooltrace_grounding_verdict():
    # Correctie uit: deze test gaat over het OORDEEL van de controle, niet over wat er daarna
    # gebeurt. Met correctie aan zou het verdict dat we hier meten al zijn weggewerkt.
    settings = make_settings(enable_planning=False, grounding_correct=False)
    graph = FakeGraph(result=f"<{ART_IRI}> bwb:tekst 'x' .")
    llm = FakeLLM([
        response([tool_block("t1", "get_artikel", {"bwb_id": "BWBR0004770", "artikel": "9"})], "tool_use"),
        response([text_block(f"Zie {ART_IRI}. (verzonnen: BWBR9999999)")], "end_turn"),
    ])
    events = _run(answer_stream("vraag", settings=settings, llm=llm, graph=graph))
    sources = next(e for e in events if e["type"] == "sources")["sources"]
    grounding = next(e for e in events if e["type"] == "grounding")
    assert ART_IRI in [s["uri"] for s in sources]
    assert grounding["grounded"] is False                    # verzonnen BWB niet in trace
    assert any("BWBR9999999" in u for u in grounding["unsupported"])


def test_grounding_correctie_doet_extra_ronde():
    settings = make_settings(enable_planning=False, grounding_correct=True)
    graph = FakeGraph(result="")  # geen tools → verzonnen citatie blijft ongegrond
    llm = FakeLLM([
        response([text_block("Antwoord met verzonnen BWBR9999999.")], "end_turn"),  # ronde 1: ongegrond
        response([text_block("Herzien antwoord zonder citatie.")], "end_turn"),      # correctie-ronde
    ])
    events = _run(answer_stream("vraag", settings=settings, llm=llm, graph=graph))
    grounding = next(e for e in events if e["type"] == "grounding")
    assert llm.index == 2                      # beide agent-rondes verbruikt (correctie liep)
    assert grounding["grounded"] is True       # na correctie gegrond
    assert "done" in [e["type"] for e in events]


def test_max_turns_kapt_af_zonder_orphan_tooluse():
    # H1: bij max_turns met nog openstaande tools mag er geen orphan tool_use in de gepersisteerde
    # messages belanden (die zou de vólgende beurt op Anthropic 400 laten crashen). De agent kapt af,
    # laat de tools vallen en levert een net (niet-leeg) antwoord i.p.v. een lege beurt.
    settings = make_settings(enable_planning=False, max_turns=2)
    graph = FakeGraph(result=f"<{ART_IRI}> bwb:tekst 'x' .")
    llm = FakeLLM([
        response([tool_block("t1", "get_artikel", {"bwb_id": "BWBR0004770", "artikel": "9"})], "tool_use"),
        response([tool_block("t2", "get_artikel", {"bwb_id": "BWBR0004770", "artikel": "9"})], "tool_use"),
    ])
    events = _run(answer_stream("vraag", settings=settings, llm=llm, graph=graph))
    types = [e["type"] for e in events]
    assert "error" not in types
    assert "done" in types
    assert llm.index == 2                 # gestopt op de cap; geen 3e agent-call
    assert len(graph.queries) == 1        # alleen de 1e beurt voerde tools uit; de 2e viel weg
    token = "".join(e["content"] for e in events if e["type"] == "token")
    assert token.strip()                  # niet-leeg antwoord (de afkap-melding)


def test_narratie_reason_antwoord_token_gescheiden():
    # Contract: de tool-narratie (het denkproces) stroomt als `reason`, het eindantwoord (de tool-loze
    # beurt) als `token`. De twee mogen niet vermengen — zo kan de werkplek ze los tonen.
    settings = make_settings(enable_planning=False)
    graph = FakeGraph(result=f"<{ART_IRI}> bwb:tekst 'x' .")
    llm = FakeLLM([
        response([
            text_block("Ik zoek nu op."),
            tool_block("t1", "get_artikel", {"bwb_id": "BWBR0004770", "artikel": "9"}),
        ], "tool_use"),
        response([text_block("De definitie is helder.")], "end_turn"),
    ])
    events = _run(answer_stream("vraag", settings=settings, llm=llm, graph=graph))
    reason = "".join(e["content"] for e in events if e["type"] == "reason")
    token = "".join(e["content"] for e in events if e["type"] == "token")
    assert "Ik zoek nu op." in reason and "Ik zoek nu op." not in token   # narratie → reason, niet in token
    assert token == "De definitie is helder."                             # eindantwoord → token (schoon)
    # (Het eindantwoord staat óók in reason — de antwoordbeurt streamt als denkproces en de frontend
    #  klapt dat blok dicht zodra het antwoord landt. Bewuste tradeoff: geen extra call/flikkering.)


def test_beurt_narratie_krijgt_alinea_scheiding_in_reason():
    # Regressie: tekst van beurt 1 ("…op.") plakte aan beurt 2 ("…tweede stap.") vast omdat de deltas
    # met "" werden samengevoegd. Op de beurt-grens hoort nu één alinea-scheiding — in de reason-stroom.
    settings = make_settings(enable_planning=False)
    graph = FakeGraph(result=f"<{ART_IRI}> bwb:tekst 'x' .")
    llm = FakeLLM([
        response([
            text_block("Ik zoek nu op."),
            tool_block("t1", "get_artikel", {"bwb_id": "BWBR0004770", "artikel": "9"}),
        ], "tool_use"),
        response([
            text_block("Nu de tweede stap."),
            tool_block("t2", "get_artikel", {"bwb_id": "BWBR0004770", "artikel": "10"}),
        ], "tool_use"),
        response([text_block("De definitie is helder.")], "end_turn"),
    ])
    events = _run(answer_stream("vraag", settings=settings, llm=llm, graph=graph))
    reason = "".join(e["content"] for e in events if e["type"] == "reason")
    assert "op.Nu" not in reason                                  # niet meer vastgeplakt
    assert "Ik zoek nu op.\n\nNu de tweede stap." in reason       # alinea-scheiding op de beurt-grens


def test_decompositie_deelvragen_retrieval_en_synthese():
    settings = make_settings(enable_decomposition=True)
    graph = FakeGraph(result=f"<{ART_IRI}> bwb:tekst 'zes weken' .")
    llm = FakeLLM([
        response([text_block("SPECIALIST: algemeen\nPLAN: opsplitsen")], "end_turn"),               # router
        response([text_block("1. Wat is de termijn?\n2. Wie is de belastingschuldige?")], "end_turn"),  # decompose
        response([tool_block("t1", "get_artikel", {"bwb_id": "BWBR0004770", "artikel": "9"})], "tool_use"),  # dv1 turn1
        response([text_block(f"Termijn: zes weken ({ART_IRI}).")], "end_turn"),                       # dv1 turn2
        response([text_block(f"Belastingschuldige: degene te wiens naam ({ART_IRI}).")], "end_turn"),  # dv2 (direct)
        response([text_block(f"Samenvatting: zes weken; belastingschuldige is degene ({ART_IRI}).")], "end_turn"),  # synthese
    ])
    events = _run(answer_stream("samengestelde vraag", settings=settings, llm=llm, graph=graph))
    types = [e["type"] for e in events]

    # opsplitsing + per-deelvraag status
    assert any(e["type"] == "status" and "Decompositie · 2 deelvragen" in e["message"] for e in events)
    assert any(e["type"] == "status" and "Deelvraag 1/2" in e["message"] for e in events)
    assert any(e["type"] == "status" and "Deelvraag 2/2" in e["message"] for e in events)
    # alleen de synthese streamt tokens (deelvraag-narratie niet)
    tokens = "".join(e["content"] for e in events if e["type"] == "token")
    assert "Samenvatting" in tokens
    assert "Termijn: zes weken" not in tokens
    # retrieval echt uitgevoerd; bronnen uit de trace; volgorde sources→grounding→done
    assert graph.queries
    sources = next(e for e in events if e["type"] == "sources")["sources"]
    assert ART_IRI in [s["uri"] for s in sources]
    assert types.index("sources") < types.index("grounding") < types.index("done")


def test_decompositie_een_deelvraag_slaat_synthese_over():
    # Simpele vraag → decompose geeft één deelvraag → solve streamt direct, GEEN synthese-call.
    settings = make_settings(enable_decomposition=True)
    graph = FakeGraph(result=f"<{ART_IRI}> bwb:tekst 'zes weken' .")
    llm = FakeLLM([
        response([text_block("SPECIALIST: algemeen\nPLAN: direct")], "end_turn"),           # router
        response([text_block("1. Wat is de termijn?")], "end_turn"),                          # decompose (één regel)
        response([tool_block("t1", "get_artikel", {"bwb_id": "BWBR0004770", "artikel": "9"})], "tool_use"),  # solve turn1
        response([text_block(f"Termijn: zes weken ({ART_IRI}).")], "end_turn"),               # solve turn2 (antwoord)
        # géén synthese-respons: als synthesize tóch liep, zou FakeLLM._next een IndexError geven.
    ])
    events = _run(answer_stream("vraag", settings=settings, llm=llm, graph=graph))
    assert llm.index == 4                                    # router+decompose+2×solve; synthese niet gedraaid
    assert not any("Opgesplitst in" in e.get("message", "") for e in events)
    # het sub-antwoord is direct gestreamd
    tokens = "".join(e["content"] for e in events if e["type"] == "token")
    assert "Termijn: zes weken" in tokens
    sources = next(e for e in events if e["type"] == "sources")["sources"]
    assert ART_IRI in [s["uri"] for s in sources]
    assert "done" in [e["type"] for e in events]


def test_decompositie_uit_geen_deelvraag_status():
    # Regressie: met de toggle uit is er geen decompositie-gedrag.
    settings = make_settings(enable_planning=False)
    graph = FakeGraph(result=ART_IRI)
    llm = FakeLLM([response([text_block("Direct antwoord.")], "end_turn")])
    events = _run(answer_stream("vraag", settings=settings, llm=llm, graph=graph))
    assert not any(e["type"] == "status" and "Deelvraag" in e.get("message", "") for e in events)


def test_geen_planning_geen_plan_status():
    settings = make_settings(enable_planning=False)
    graph = FakeGraph(result=ART_IRI)
    llm = FakeLLM([response([text_block("Direct antwoord.")], "end_turn")])
    events = _run(answer_stream("vraag", settings=settings, llm=llm, graph=graph))
    assert not any(e["type"] == "status" and "Aanpak" in e.get("message", "") for e in events)


def test_leeg_antwoord_levert_melding_geen_stilte():
    """Een lege antwoordbeurt mag nooit als stilte bij de gebruiker landen.

    De frontend toonde dan zijn fallback "(geen antwoord)" naast een lijst bronnen, zonder spoor in
    de logs. finalize_node vangt dat nu af met een expliciete melding (en een warning-logregel).
    """
    settings = make_settings(enable_planning=False)
    graph = FakeGraph(result=f"<{ART_IRI}> bwb:tekst 'x' .")
    llm = FakeLLM([
        response([tool_block("t1", "get_artikel", {"bwb_id": "BWBR0004770", "artikel": "9"})], "tool_use"),
        response([text_block("   ")], "end_turn"),   # lege tekstbeurt → answer blijft leeg
    ])
    events = _run(answer_stream("vraag", settings=settings, llm=llm, graph=graph))

    tokens = "".join(e["content"] for e in events if e["type"] == "token")
    assert tokens.strip(), "finalize moet een melding streamen bij een leeg antwoord"
    assert "geen antwoord formuleren" in tokens
    # de bronnen blijven gewoon meekomen
    assert any(e["type"] == "sources" for e in events)
    assert "done" in [e["type"] for e in events]


def test_deelvraag_beurtlimiet_dwingt_antwoord_af():
    """Raakt de deelvraag-lus zijn beurtlimiet, dan moet er alsnog een antwoord komen.

    Eerder brak de lus alleen af als het model géén tools meer aanriep; bleef het zoeken, dan liep de
    lus af met een leeg `antwoord` en zag de gebruiker alleen bronnen. Op de laatste beurt worden nu
    geen tools meer aangeboden, zodat het model wel moet antwoorden op wat er is opgehaald.
    """
    # sub_max_turns=2: de eerste beurt zoekt nog, de tweede is de laatste en krijgt geen tools meer.
    settings = make_settings(enable_planning=False, enable_decomposition=True, sub_max_turns=2)
    graph = FakeGraph(result=f"<{ART_IRI}> bwb:tekst 'x' .")
    llm = FakeLLM([
        response([text_block("supervisor")], "end_turn"),                                    # supervisor
        response([text_block('{"deelvragen": ["Wat is een belastingschuldige?"]}')], "end_turn"),  # decompose
        response([tool_block("t1", "get_artikel", {"bwb_id": "BWBR0004770", "artikel": "9"})], "tool_use"),
        response([text_block(f"Volgens {ART_IRI} is dat X.")], "end_turn"),  # laatste beurt: tools-loos
    ])
    events = _run(answer_stream("vraag", settings=settings, llm=llm, graph=graph))

    tokens = "".join(e["content"] for e in events if e["type"] == "token")
    assert "Volgens" in tokens, "de laatste beurt moet een echt antwoord opleveren"
    assert "geen antwoord formuleren" not in tokens, "het finalize-vangnet mag niet nodig zijn"
    assert any(e["type"] == "status" and "beurtlimiet bereikt" in e.get("message", "") for e in events)


def test_correctie_op_een_citaat_dat_niet_letterlijk_is():
    """De correctieronde moet zeggen wat er écht mis is.

    Hij keek alleen naar `unsupported` (verzonnen vindplaatsen). Een antwoord dat daarop schoon is
    maar wél passages tussen aanhalingstekens zet die niet in de bron staan — op dev zeven keer in
    één antwoord — kreeg dan een volledige extra LLM-call met de instructie "je noemde
    verwijzing(en) `` die niet uit de graaf kwamen": een lege opsomming en een verwijt dat niet
    klopte. Het model kan daar niets mee, dus de duurste stap in de keten deed niets.
    """
    settings = make_settings(enable_planning=False, grounding_correct=True)
    bron = "De ontvanger verleent uitstel van betaling indien de schuldenaar daarom verzoekt."
    graph = FakeGraph(result=f"<{ART_IRI}> bwb:tekst '{bron}' .")
    llm = FakeLLM([
        response([tool_block("t1", "get_artikel", {"bwb_id": "BWBR0004770", "artikel": "9"})], "tool_use"),
        # Een "citaat" met een eigen weglating erin: geen verzonnen vindplaats, wel een parafrase
        # die als letterlijk wordt gepresenteerd.
        response([text_block(
            f'Zie {ART_IRI}: "De ontvanger verleent uitstel (...) indien de schuldenaar verzoekt."'
        )], "end_turn"),
        response([text_block(f"Zie {ART_IRI}: de ontvanger kan uitstel verlenen.")], "end_turn"),
    ])
    events = _run(answer_stream("vraag", settings=settings, llm=llm, graph=graph))

    assert llm.index == 3, "de correctieronde hoort te zijn gedraaid"
    instructie = llm.calls[-1]["messages"][-1]["content"]
    assert "niet letterlijk" in instructie
    assert "De ontvanger verleent uitstel" in instructie, "het model moet weten wélk citaat"
    assert "verwijzing(en) ," not in instructie and "verwijzing(en) ." not in instructie
    assert next(e for e in events if e["type"] == "grounding")["grounded"] is True


def test_correctie_noemt_beide_soorten_als_beide_mis_zijn():
    settings = make_settings(enable_planning=False, grounding_correct=True)
    bron = "De ontvanger verleent uitstel van betaling."
    graph = FakeGraph(result=f"<{ART_IRI}> bwb:tekst '{bron}' .")
    llm = FakeLLM([
        response([tool_block("t1", "get_artikel", {"bwb_id": "BWBR0004770", "artikel": "9"})], "tool_use"),
        response([text_block(
            'Zie BWBR9999999: "De ontvanger verleent uitstel aan iedere schuldenaar zonder meer."'
        )], "end_turn"),
        response([text_block("Herzien antwoord zonder citaat.")], "end_turn"),
    ])
    _run(answer_stream("vraag", settings=settings, llm=llm, graph=graph))

    instructie = llm.calls[-1]["messages"][-1]["content"]
    assert "BWBR9999999" in instructie
    assert "niet letterlijk" in instructie
