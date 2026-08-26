"""Lege tekstblokken uit messages strippen (Anthropic weigert {"type":"text","text":""})."""
from __future__ import annotations

from agent.orchestrator import _schoon_messages


def test_verwijdert_leeg_tekstblok_naast_tool_use():
    msgs = [
        {"role": "user", "content": "hoi"},
        {"role": "assistant", "content": [
            {"type": "text", "text": ""},  # leeg → weg
            {"type": "tool_use", "id": "1", "name": "get_lid", "input": {}},
        ]},
    ]
    out = _schoon_messages(msgs)
    assert out[0]["content"] == "hoi"  # string-content ongemoeid
    assert out[1]["content"] == [{"type": "tool_use", "id": "1", "name": "get_lid", "input": {}}]


def test_slaat_volledig_leeg_bericht_over_en_behoudt_echte_tekst():
    msgs = [
        {"role": "assistant", "content": [{"type": "text", "text": "   "}]},  # alleen witruimte → bericht weg
        {"role": "assistant", "content": [{"type": "text", "text": "Antwoord."}]},  # blijft
    ]
    out = _schoon_messages(msgs)
    assert len(out) == 1
    assert out[0]["content"] == [{"type": "text", "text": "Antwoord."}]
