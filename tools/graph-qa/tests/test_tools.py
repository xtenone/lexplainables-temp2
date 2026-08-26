"""WP-D: de registry levert schema's en dispatcht naar de juiste bouwer."""
from __future__ import annotations

from agent import tools
from agent.graph import schema
from fakes import FakeGraph, make_settings

EXPECTED = {
    "search_wetgeving", "semantic_search", "get_artikel", "get_lid", "get_bepaling", "list_regelingen",
    "get_regeling_info", "follow_verwijzingen", "referenced_by", "get_context",
    "resolve_begrip", "graph_schema", "raw_sparql",
}


def test_schemas_compleet_en_welgevormd():
    schemas = tools.anthropic_schemas()
    namen = {t["name"] for t in schemas}
    assert namen == EXPECTED
    for t in schemas:
        assert t["input_schema"]["type"] == "object"
        assert t["description"]


def test_anthropic_schemas_filter():
    assert len(tools.anthropic_schemas()) == 13
    subset = tools.anthropic_schemas(only={"get_artikel", "search_wetgeving"})
    assert {t["name"] for t in subset} == {"get_artikel", "search_wetgeving"}


def test_dispatch_onbekende_tool():
    assert "Onbekende tool" in tools.dispatch("bestaat_niet", FakeGraph(), {})


def test_dispatch_list_regelingen_voert_query_uit():
    g = FakeGraph(result="resultaat")
    out = tools.dispatch("list_regelingen", g, {})
    assert out == "resultaat"
    assert g.queries and "bwb:Regeling" in g.queries[0]


def test_dispatch_get_artikel():
    g = FakeGraph(result="artikel 9")
    out = tools.dispatch("get_artikel", g, {"bwb_id": "BWBR0004770", "artikel": "9"})
    assert out == "artikel 9"
    assert ":artikel:9>" in g.queries[0]


def test_dispatch_vangt_validatiefout_op():
    g = FakeGraph()
    out = tools.dispatch("get_artikel", g, {"bwb_id": "kwaadaardig", "artikel": "9"})
    assert out.startswith("Fout bij tool 'get_artikel'")
    assert not g.queries  # query is nooit uitgevoerd


def test_dispatch_vangt_transportfout_op():
    # F1: een httpx-transportfout (timeout/connection-reset) tijdens een tool-call mag de agent-beurt
    # niet breken — dispatch geeft 'm als tool-resultaat terug zodat de agent kan herstellen.
    import httpx

    def _kapot(_q: str) -> str:
        raise httpx.ConnectError("connection refused")

    g = FakeGraph(results=_kapot)
    out = tools.dispatch("get_artikel", g, {"bwb_id": "BWBR0004770", "artikel": "9"})
    assert out.startswith("Fout bij tool 'get_artikel'")
    assert "onbereikbaar" in out.lower()


def test_dispatch_raw_sparql_forwards_query():
    g = FakeGraph(result="rows")
    tools.dispatch("raw_sparql", g, {"query": "SELECT ?s WHERE { ?s ?p ?o }"})
    assert g.queries == ["SELECT ?s WHERE { ?s ?p ?o }"]


def test_dispatch_get_context():
    g = FakeGraph(result="subgraaf")
    out = tools.dispatch("get_context", g, {"bwb_id": "BWBR0004770", "artikel": "9"})
    assert out == "subgraaf"
    q = g.queries[0]
    assert "verwijzingDoor" in q and "heeftVerwijzing" in q and "bwb:bevat" in q


def test_semantic_search_zonder_index_degradeert():
    g = FakeGraph(result="treffers")
    out = tools.dispatch("semantic_search", g, {"query": "belasting te laat"}, make_settings())
    assert "niet geconfigureerd" in out.lower()
    assert g.semantic_queries == []  # graaf niet geraakt


def test_semantic_search_met_index_roept_graaf():
    g = FakeGraph(result="treffers")
    settings = make_settings(similarity_index="bwb_similarity")
    out = tools.dispatch("semantic_search", g, {"query": "belasting te laat"}, settings)
    assert out == "treffers"
    assert g.semantic_queries == ["belasting te laat"]


def test_semantic_search_limit_geclampt():
    # L5: limit clampen 1–50 en niet-int gracieus terugvallen op de default (10).
    from types import SimpleNamespace

    from agent.tools import _h_semantic_search

    captured: dict[str, int] = {}

    class G:
        def semantic_search(self, query: str, limit: int = 10) -> str:
            captured["limit"] = limit
            return ""

    s = SimpleNamespace(similarity_index="bwb_similarity")
    _h_semantic_search(G(), {"query": "x", "limit": 100000}, s)
    assert captured["limit"] == 50
    _h_semantic_search(G(), {"query": "x", "limit": 0}, s)
    assert captured["limit"] == 1
    _h_semantic_search(G(), {"query": "x", "limit": "abc"}, s)
    assert captured["limit"] == 10
