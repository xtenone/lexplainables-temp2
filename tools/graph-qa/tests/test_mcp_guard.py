"""Read-only vangnet: alleen lees-vormen (SELECT/ASK/CONSTRUCT/DESCRIBE) mogen erdoor.

De guard werkte eerder met een blocklist van update-sleutelwoorden, en die was te omzeilen: LOAD,
CLEAR en DROP werden alleen aan het begin van een REGEL herkend, dus achter een PREFIX op dezelfde
regel liepen ze er doorheen. De `BYPASS`-gevallen hieronder zijn precies die vormen; ze horen bij
een allowlist vanzelf te sneuvelen.
"""
from __future__ import annotations

import pytest

from agent.mcp_client import MCPClient, MCPError, _looks_like_update

UPDATES = [
    "INSERT DATA { <a> <b> <c> }",
    "DELETE WHERE { ?s ?p ?o }",
    "DELETE { ?s ?p ?o } WHERE { ?s ?p ?o }",
    "DROP GRAPH <http://x>",
    "CLEAR ALL",
    "LOAD <http://x>",
    "PREFIX ex: <http://x#>\nINSERT DATA { ex:a ex:b ex:c }",
    "WITH <http://g> DELETE { ?s ?p ?o } INSERT { ?s ?p 1 } WHERE { ?s ?p ?o }",
    "",                       # niets uitvoerbaars is ook geen leesquery
    "vertel me over artikel 9",  # proza dat per ongeluk als query wordt aangeboden
]

# Vormen die de oude blocklist doorliet omdat het verb niet aan het regelbegin stond.
BYPASS = [
    "PREFIX x: <http://a/> LOAD <http://evil/x.ttl>",
    "PREFIX x: <http://a/> CLEAR GRAPH <urn:bwb:BWBR0004770>",
    "PREFIX x: <http://a/> DROP GRAPH <http://g>",
    "# onschuldig ogend commentaar\nPREFIX x: <http://a/> COPY <http://a> TO <http://b>",
]

BENIGN = [
    "SELECT ?s WHERE { ?s ?p ?o } LIMIT 10",
    'SELECT ?t WHERE { ?s bwb:tekst ?t FILTER(CONTAINS(LCASE(?t), "delete")) }',
    "PREFIX bwb: <urn:bwb-ns:>\nSELECT (COUNT(DISTINCT ?w) AS ?n) WHERE { ?w a bwb:Regeling }",
    "ASK { ?s ?p ?o }",
    "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
    "BASE <http://x/> PREFIX a: <b#> CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
    # De prefix-IRI eindigt op '#'; dat mag niet als commentaar worden weggeknipt, anders sneuvelt
    # de declaratie en lijkt een doodgewone Lucene-query ineens geen leesquery meer.
    "PREFIX luc: <http://www.ontotext.com/connectors/lucene#>\nSELECT ?n WHERE { ?n luc:score ?s }",
    "# eerst even uitleggen wat ik doe\nSELECT ?s WHERE { ?s ?p ?o }",
    'SELECT ?t WHERE { ?s bwb:tekst "nr. #3 DROP GRAPH <http://g>" }',
]


@pytest.mark.parametrize("q", UPDATES)
def test_updates_herkend(q):
    assert _looks_like_update(q) is True


@pytest.mark.parametrize("q", BYPASS)
def test_update_achter_een_prefix_wordt_ook_geweigerd(q):
    """De regressie: de blocklist keek naar het regelbegin, dus dit glipte erdoor."""
    assert _looks_like_update(q) is True


@pytest.mark.parametrize("q", BENIGN)
def test_benigne_queries_niet_herkend(q):
    assert _looks_like_update(q) is False


def test_reject_updates_gooit_mcperror():
    with pytest.raises(MCPError):
        MCPClient._reject_updates({"query": "INSERT DATA { <a> <b> <c> }"})


def test_reject_updates_laat_select_door():
    # Mag geen exception geven.
    MCPClient._reject_updates({"query": "SELECT ?s WHERE { ?s ?p ?o }"})


def _client(monkeypatch) -> MCPClient:
    c = MCPClient(url="http://x/mcp", token="t")
    monkeypatch.setattr(c, "_rpc", lambda *a, **k: {"content": []})  # geen netwerk
    return c


def test_semantic_search_verb_query_niet_geweigerd(monkeypatch):
    # M2: de guard hoort op de SPARQL-string, niet op elk tool-argument. Een natuurlijke-taal-query
    # voor similarity_search die met een verb begint of 'insert data' bevat, mag niet stuklopen.
    c = _client(monkeypatch)
    for q in ("insert data over de BRP", "Add-on regelingen bij de IW", "clear inzicht in verjaring"):
        assert c.semantic_search(q) == ""  # geen MCPError


def test_raw_sparql_update_nog_steeds_geweigerd(monkeypatch):
    # De guard blijft wél gelden voor de rauwe SPARQL-route (sparql()).
    c = _client(monkeypatch)
    with pytest.raises(MCPError):
        c.sparql("INSERT DATA { <a> <b> <c> }")
    assert c.sparql("SELECT ?s WHERE { ?s ?p ?o }") == ""  # SELECT gewoon door
