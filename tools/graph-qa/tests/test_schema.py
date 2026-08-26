"""WP-D: schema-introspectie draait de introspectiequery's en cachet ze."""
from __future__ import annotations

import pytest

from agent.graph import schema
from fakes import FakeGraph


@pytest.fixture(autouse=True)
def _clear_cache():
    schema.reset_cache()
    yield
    schema.reset_cache()


def test_graph_schema_bevat_tellingen_en_regelingen():
    g = FakeGraph(result="DATA")
    out = schema.graph_schema(g)
    assert "AANTALLEN PER TYPE" in out
    assert "REGELINGEN" in out
    assert len(g.queries) == 2  # count_by_type + list_regelingen


def test_graph_schema_wordt_gecachet():
    g = FakeGraph(result="DATA")
    schema.graph_schema(g)
    schema.graph_schema(g)  # tweede aanroep
    assert len(g.queries) == 2  # graaf niet opnieuw geraakt
