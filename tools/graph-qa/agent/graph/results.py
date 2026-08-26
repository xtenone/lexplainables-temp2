"""Parse SPARQL Query Results TSV (W3C) — het formaat dat de GraphDB-MCP voor een SELECT teruggeeft.

De eerste regel bevat de `?var`-namen (tab-gescheiden); elke volgende regel is één resultaatrij met
tab-gescheiden RDF-termen:
  - IRI's als `<...>`
  - literals als `"..."`, optioneel met `@taal` of `^^<type>`
  - een lege cel = unbound
Tabs en newlines bínnen een literal zijn ge-escaped (`\\t`/`\\n`), dus één fysieke regel == één rij.
We leveren per rij een dict {var: platte-waarde} — voor onze SELECT-queries (leden-teksten,
regeling-info) is dat voldoende; datatypes/talen worden afgepeld tot de kale waarde.
"""
from __future__ import annotations

import json
import re

_LITERAL = re.compile(r'^"(.*)"(?:@[\w-]+|\^\^\S+)?$', re.DOTALL)
_ESCAPES = {"t": "\t", "n": "\n", "r": "\r", "\\": "\\", '"': '"', "'": "'"}


def _unescape(s: str) -> str:
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "\\" and i + 1 < n:
            out.append(_ESCAPES.get(s[i + 1], s[i + 1]))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _decode_term(term: str) -> str:
    t = term.strip()
    if not t:
        return ""
    if t.startswith("<") and t.endswith(">"):
        return t[1:-1]
    m = _LITERAL.match(t)
    if m:
        return _unescape(m.group(1))
    return t  # kaal getal/boolean


def parse_select(tsv: str) -> list[dict[str, str]]:
    """Parseer SPARQL-TSV naar rijen [{var: waarde}]. Lege/ongeldige invoer → []."""
    raw = (tsv or "").strip()
    # De GraphDB-MCP levert de TSV JSON-string-encoded (begint met `"`, met \t/\n/\" als escapes).
    # Pel die buitenste laag er eerst af; kreeg je al kale TSV (met echte tabs), dan sla je dit over.
    if raw.startswith('"'):
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, str):
                tsv = decoded
        except json.JSONDecodeError:
            pass
    lines = (tsv or "").split("\n")
    while lines and lines[-1].strip() == "":
        lines.pop()
    if not lines:
        return []
    header = [h.strip().lstrip("?") for h in lines[0].split("\t")]
    rows: list[dict[str, str]] = []
    for line in lines[1:]:
        if line.strip() == "":
            continue
        cells = line.split("\t")
        rows.append({header[i]: (_decode_term(cells[i]) if i < len(cells) else "") for i in range(len(header))})
    return rows
