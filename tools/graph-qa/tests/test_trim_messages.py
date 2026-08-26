"""F2: _trim_messages begrenst de historie naar de LLM met behoud van tool_use/tool_result-integriteit."""
from __future__ import annotations

from agent.orchestrator import _snoei_historie, _trim_messages, _voeg_toe_en_snoei


def _u(text: str) -> dict:
    return {"role": "user", "content": text}


def _a(text: str) -> dict:
    return {"role": "assistant", "content": text}


def _a_tool(tid: str, naam: str = "get_lid") -> dict:
    return {"role": "assistant", "content": [{"type": "tool_use", "id": tid, "name": naam, "input": {}}]}


def _r(tid: str, tekst: str) -> dict:
    return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": tekst}]}


def _geen_orphan(msgs: list[dict]) -> bool:
    """Elke tool_result heeft een voorafgaand assistant-tool_use met hetzelfde id in de kept-lijst."""
    gezien: set[str] = set()
    for m in msgs:
        c = m.get("content")
        if m["role"] == "assistant" and isinstance(c, list):
            gezien |= {b["id"] for b in c if isinstance(b, dict) and b.get("type") == "tool_use"}
        if m["role"] == "user" and isinstance(c, list):
            for b in c:
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") not in gezien:
                    return False
    return True


CONV = [
    _u("eerdere vraag 1"),
    _a_tool("t1"), _r("t1", "x" * 200),
    _u("eerdere vraag 2"),
    _a_tool("t2"), _r("t2", "y" * 200),
    _u("huidige vraag"),
]


def test_uit_bij_nul_of_leeg():
    assert _trim_messages(CONV, 0) == CONV
    assert _trim_messages([], 100) == []


def test_ruim_budget_ongewijzigd():
    assert _trim_messages(CONV, 10_000) == CONV


def test_klein_budget_respecteert_venster_en_invarianten():
    for budget in (50, 120, 250, 500, 900):
        kept = _trim_messages(CONV, budget)
        assert kept, "nooit leeg"
        assert kept[-1] == CONV[-1], "huidige vraag altijd behouden"
        assert kept[0]["role"] == "user" and isinstance(kept[0]["content"], str), "start = echte user-message"
        assert _geen_orphan(kept), "geen orphan tool_result"


def test_orphan_tool_result_vooraan_valt_weg():
    # Budget dat het venster midden in het t2-paar laat beginnen → de orphan tool_result (+ evt. losse
    # assistant) valt vooraan weg; de huidige vraag blijft.
    kept = _trim_messages(CONV, 210)
    assert _geen_orphan(kept)
    assert kept[0]["role"] == "user" and isinstance(kept[0]["content"], str)
    assert CONV[-1] in kept


# Reeks zoals agent_node die ná tools_node ziet: eindigt op een tool_result, en de enige platte
# user-beurt (de vraag) staat vér vooraan. Een krap budget mag géén orphan tool_result opleveren.
CONV_EINDIGT_OP_RESULT = [
    _u("de vraag"),
    _a_tool("t1"), _r("t1", "x" * 8000),
    _a_tool("t2"), _r("t2", "y" * 8000),
    _a_tool("t3"), _r("t3", "z" * 8000),
]


def test_venster_zonder_platte_user_wordt_teruguitgebreid():
    # Budget < één paar → het budget-venster bevat puur tool-paren; de trimmer moet terug-uitbreiden
    # tot de vraag i.p.v. terug te vallen op een losse (orphan) tool_result.
    for budget in (100, 5000, 8000, 15000):
        kept = _trim_messages(CONV_EINDIGT_OP_RESULT, budget)
        assert kept, "nooit leeg"
        assert _geen_orphan(kept), f"geen orphan bij budget {budget}"
        assert kept[0] == CONV_EINDIGT_OP_RESULT[0], "begint bij de platte user-vraag"


# --- De opslagrem: wat er in de checkpointer blijft staan ----------------------------------------
#
# `max_history_chars` begrenst wat er per beurt naar het model gaat; zonder een tweede rem groeide
# de BEWAARDE historie onbeperkt door — inclusief elk tool-resultaat van 8000 tekens. Elke
# checkpoint-write in een lang gesprek werd daar trager en dikker van.

def test_korte_historie_blijft_ongemoeid():
    msgs = [_u("vraag"), _a("antwoord")]
    assert _snoei_historie(msgs, 10_000) == msgs


def test_snoeien_knipt_op_een_platte_user_beurt():
    """Een losgeknipt tool_result mist zijn tool_use, en dan weigert Anthropic de hele request —
    een te grote historie is hinderlijk, een kapotte is fataal."""
    lang = "x" * 400
    msgs = [
        _u("eerste vraag"),
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "get_lid", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": lang}]},
        _a(lang),
        _u("tweede vraag"),
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t2", "name": "get_lid", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t2", "content": lang}]},
        _a("klaar"),
    ]

    uit = _snoei_historie(msgs, 900)

    assert uit[0]["role"] == "user" and isinstance(uit[0]["content"], str), "begint op een platte user"
    assert len(uit) < len(msgs), "er is daadwerkelijk gesnoeid"
    # Elk overgebleven tool_result heeft zijn tool_use nog vóór zich.
    open_ids = set()
    for m in uit:
        inhoud = m.get("content")
        if isinstance(inhoud, list):
            for blok in inhoud:
                if blok.get("type") == "tool_use":
                    open_ids.add(blok["id"])
                if blok.get("type") == "tool_result":
                    assert blok["tool_use_id"] in open_ids, "orphan tool_result overgebleven"


def test_zonder_veilige_grens_wordt_er_niet_gesnoeid():
    """Liever een te grote historie dan een historie die de volgende beurt laat crashen."""
    msgs = [
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "x", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "y" * 5000}]},
    ]
    assert _snoei_historie(msgs, 100) == msgs


def test_de_reducer_voegt_toe_en_snoeit():
    msgs = _voeg_toe_en_snoei([_u("a")], [_a("b")])
    assert [m["role"] for m in msgs] == ["user", "assistant"]
