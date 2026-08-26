"""De supervisor: welke workers draaien er, en wanneer draait er géén.

Twee dingen die eerder ontbraken. De workerlijst werd niet gevalideerd, dus elke naam die het model
verzon werd stilzwijgend een extra ANTWOORD-worker — dezelfde vraag twee keer beantwoord, dubbele
kosten. En "AFWIJZEN" stond wel in het promptformaat maar werd nergens gelezen: het ging als plan de
systeemprompt van een specialist in, waarna een tweede modelbeslissing bepaalde wat er gebeurde.
"""
from __future__ import annotations

import asyncio

from agent.agent import _recursielimiet, answer_stream
from agent.supervisor import SUPERVISOR_SYSTEM, parse_supervisor
from fakes import FakeGraph, FakeLLM, make_settings, response, text_block


def _run(gen):
    async def collect():
        return [ev async for ev in gen]

    return asyncio.run(collect())


# --- de workerlijst ------------------------------------------------------------------------------

def test_onbekende_worker_telt_niet_mee():
    plan, _, _ = parse_supervisor("WORKERS: antwoord, samenvatten\nSPECIALIST: duiding\nPLAN: x")
    assert plan == ["duiding"], "een verzonnen workernaam mag geen tweede beurt opleveren"


def test_lege_of_onzinnige_workerlijst_valt_terug_op_antwoord():
    for regel in ("WORKERS: geen", "WORKERS:", "SPECIALIST: algemeen"):
        plan, _, _ = parse_supervisor(f"{regel}\nPLAN: x")
        assert plan == ["algemeen"]


def test_keten_wordt_gecapt():
    plan, _, _ = parse_supervisor(
        "WORKERS: annotatie, antwoord, annotatie, antwoord\nSPECIALIST: duiding\nPLAN: x"
    )
    assert plan == ["annotatie", "duiding"]


def test_annotatie_en_antwoord_ketenen_blijft_mogelijk():
    plan, _, _ = parse_supervisor("WORKERS: annotatie, antwoord\nSPECIALIST: duiding\nPLAN: x")
    assert plan == ["annotatie", "duiding"]


# --- afwijzen ------------------------------------------------------------------------------------

def test_afwijzen_wordt_herkend():
    _, _, afwijzen = parse_supervisor("WORKERS: antwoord\nSPECIALIST: algemeen\nPLAN: AFWIJZEN")
    assert afwijzen is True


def test_gewoon_plan_is_geen_afwijzing():
    _, _, afwijzen = parse_supervisor("WORKERS: antwoord\nSPECIALIST: duiding\nPLAN: zoek artikel 9 op")
    assert afwijzen is False


def test_afgewezen_vraag_kost_geen_tweede_llm_call():
    """De hele winst: geen specialist, geen tools, geen graafverkeer — één beleefde melding."""
    llm = FakeLLM([
        response([text_block("WORKERS: antwoord\nSPECIALIST: algemeen\nPLAN: AFWIJZEN")], "end_turn"),
    ])
    graaf = FakeGraph(result="")
    events = _run(answer_stream(
        "Hoeveel is 17 maal 23?",
        settings=make_settings(), llm=llm, graph=graaf,
    ))

    assert llm.index == 1, "alleen de supervisor-call, geen specialist"
    assert graaf.queries == [], "een afgewezen vraag hoort de graaf niet te raken"
    tekst = "".join(e.get("content", "") for e in events if e["type"] == "token")
    assert "wet- en regelgeving" in tekst and "annoteren" in tekst  # zegt óók wat wél kan
    assert [e["type"] for e in events][-1] == "done"
    assert not any(e["type"] == "sources" for e in events)


def test_afwijzing_geldt_de_vraag_niet_het_gesprek():
    """De vlag moet per beurt gereset worden; anders blijft de hele thread afwijzen."""
    llm = FakeLLM([
        response([text_block("WORKERS: antwoord\nSPECIALIST: algemeen\nPLAN: AFWIJZEN")], "end_turn"),
        # Tweede beurt, zelfde thread: nu een gewone vraag.
        response([text_block("WORKERS: antwoord\nSPECIALIST: duiding\nPLAN: zoek art. 9 op")], "end_turn"),
        response([text_block("Artikel 9 gaat over de invorderingstermijn.")], "end_turn"),
    ])
    instellingen = make_settings()
    graaf = FakeGraph(result="")
    _run(answer_stream("Wat is het weer?", "gesprek-1", settings=instellingen, llm=llm, graph=graaf))
    events = _run(answer_stream(
        "Waar gaat artikel 9 IW over?", "gesprek-1", settings=instellingen, llm=llm, graph=graaf,
    ))

    tekst = "".join(e.get("content", "") for e in events if e["type"] == "token")
    assert "invorderingstermijn" in tekst, "de tweede vraag hoort gewoon beantwoord te worden"


# --- de stappenlimiet ----------------------------------------------------------------------------

def test_recursielimiet_dekt_een_volle_annotatieketen():
    """De oude formule (`max_turns * 2 + 10`) telde alleen de agent-lus: één annotatie-worker die
    zijn beurtlimiet vol gebruikt zat al op ~49 van de 50 stappen, en twee workers gingen eroverheen."""
    s = make_settings(max_turns=20, critic_max_rondes=2)
    een_worker = 2 * s.max_turns + 6 + 2 * s.critic_max_rondes
    assert _recursielimiet(s) >= 2 * een_worker


# --- de grens van AFWIJZEN ------------------------------------------------------------------------

def test_prompt_beperkt_afwijzen_tot_niet_wetgeving():
    """Afwijzen mag om de vráág, niet om een vermoeden over de inhoud van de graaf.

    De instructie zei "AFWIJZEN als de vraag niet over de Nederlandse wet- en regelgeving IN DE GRAAF
    gaat", en dat voegde twee dingen samen die uit elkaar horen. Of iets over wetgeving gaat weet de
    supervisor zonder te kijken; of een bepáálde regeling in de graaf zit juist niet — hij heeft geen
    tools. Op dev wees hij daardoor een vraag over "de milieuwet" af, terwijl art. 36 IW 1990 de Wet
    belastingen op milieugrondslag noemt: er was wél iets te vinden.
    """
    prompt = SUPERVISOR_SYSTEM
    assert "AFWIJZEN als de vraag niet over Nederlandse wet- en regelgeving gaat" in prompt
    # De supervisor moet expliciet te horen krijgen dat "ken ik niet" geen grond is.
    assert "niet in de graaf zit" in prompt
    assert "niet aan jou om te weten" in prompt


def test_afwijsmelding_claimt_niets_over_de_graaf():
    """De melding mag niet suggereren dat de bepaling is opgezocht — er is niet gekeken."""
    llm = FakeLLM([
        response([text_block("WORKERS: antwoord\nSPECIALIST: algemeen\nPLAN: AFWIJZEN")], "end_turn"),
    ])
    events = _run(answer_stream(
        "Hoeveel is 17 maal 23?", settings=make_settings(), llm=llm, graph=FakeGraph(result=""),
    ))
    tekst = "".join(e.get("content", "") for e in events if e["type"] == "token")
    assert "kennisgraaf" not in tekst, "zonder te kijken kun je niets zeggen over de inhoud van de graaf"
    assert "wet- en regelgeving" in tekst
