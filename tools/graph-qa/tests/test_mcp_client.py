"""semantic_search: MCPClient bouwt de juiste similarity_search-argumenten."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.mcp_client import MCPClient, MCPError


def test_semantic_search_gebruikt_similarity_search():
    c = MCPClient(url="http://x/mcp", token="t", repository_id="inning", similarity_index="bwb_similarity")
    captured: dict = {}

    def _fake_call_tool(name, arguments):
        captured["name"] = name
        captured["arguments"] = arguments
        return [{"type": "text", "text": "resultaat"}]

    c.call_tool = _fake_call_tool  # type: ignore[assignment]
    out = c.semantic_search("belasting niet op tijd betaald", limit=5)

    assert out == "resultaat"
    assert captured["name"] == "similarity_search"
    args = captured["arguments"]
    assert args["similarityIndex"] == "bwb_similarity"
    assert args["connectorType"] == "similarity"
    assert args["repositoryId"] == "inning"
    assert args["query"] == "belasting niet op tijd betaald"


def test_rpc_non_2xx_zonder_result_raist(monkeypatch):
    # F5: een 5xx met een JSON-body zonder `result`/`error` mag niet stil een leeg resultaat geven.
    c = MCPClient(url="http://x/mcp", token="t", repository_id="inning")
    resp = SimpleNamespace(
        status_code=500,
        headers={"content-type": "application/json"},
        json=lambda: {"jsonrpc": "2.0", "id": 1},  # geen result, geen error
        text="internal error",
    )
    monkeypatch.setattr(c._client, "post", lambda *a, **k: resp)
    with pytest.raises(MCPError) as exc:
        c._rpc("tools/call", {"name": "x", "arguments": {}})
    assert "500" in str(exc.value)


def test_rpc_2xx_result_ok(monkeypatch):
    # Regressie: een gewone 200 met result blijft werken (statuscheck raakt het happy-path niet).
    c = MCPClient(url="http://x/mcp", token="t", repository_id="inning")
    resp = SimpleNamespace(
        status_code=200,
        headers={"content-type": "application/json"},
        json=lambda: {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "ok"}]}},
        text="",
    )
    monkeypatch.setattr(c._client, "post", lambda *a, **k: resp)
    assert c.call_tool("x", {}) == [{"type": "text", "text": "ok"}]
