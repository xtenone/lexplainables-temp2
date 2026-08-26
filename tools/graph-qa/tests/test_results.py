"""SPARQL-TSV-parser: header, unbound cellen, IRI-/literal-decodering, escapes."""
from __future__ import annotations

import json

from agent.graph.results import parse_select


def test_parse_json_string_encoded_tsv():
    # De GraphDB-MCP levert de TSV als JSON-string (begint met `"`, met \t/\n/\" ge-escaped).
    tsv = '?lidnummer\t?lidtekst\n"1"\t"Eerste lid."@nl'
    rows = parse_select(json.dumps(tsv))
    assert rows == [{"lidnummer": "1", "lidtekst": "Eerste lid."}]


def test_parse_leden_rijen_iri_en_literal():
    tsv = (
        "?tekst\t?jci\t?lid\t?lidnummer\t?lidtekst\n"
        '\t"jci..."\t<urn:bwb:BWBR0004770:artikel:9:lid:1>\t"1"\t"Eerste lid."@nl\n'
        '\t"jci..."\t<urn:bwb:BWBR0004770:artikel:9:lid:2>\t"2"\t"Tweede met \\"aanhaling\\"."@nl'
    )
    rows = parse_select(tsv)
    assert len(rows) == 2
    assert rows[0]["tekst"] == ""  # unbound cel
    assert rows[0]["lidnummer"] == "1"
    assert rows[0]["lidtekst"] == "Eerste lid."
    assert rows[0]["lid"] == "urn:bwb:BWBR0004770:artikel:9:lid:1"  # IRI afgepeld
    assert rows[1]["lidtekst"] == 'Tweede met "aanhaling".'  # \" ge-unescaped, @nl afgepeld


def test_parse_leeg_en_alleen_header():
    assert parse_select("") == []
    assert parse_select("?a\t?b") == []
