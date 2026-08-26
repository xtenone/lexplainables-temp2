"""
Getypeerde domein-toollaag over de kennisgraaf.

Het model kiest voortaan uit deze bewerkingen i.p.v. vrije SPARQL te schrijven:
onze code bouwt de query deterministisch (agent/graph/queries.py) en voert die uit
via de GraphPort. Elke tool draagt in zijn beschrijving het "hoe"; de correctheid
zit in geteste code, niet in prompt-proza. raw_sparql blijft als gated escape.

De registry levert twee dingen aan de loop:
  - anthropic_schemas(): de model-facing tool-schema's
  - dispatch(name, graph, args): voert de tool uit en geeft resultaattekst terug
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import httpx

from ..graph import queries, schema
from ..mcp_client import MCPError
from ..ports import GraphPort

logger = logging.getLogger("graph_qa.tools")

Handler = Callable[[GraphPort, dict[str, Any]], str]


def _obj(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


_STR = {"type": "string"}


# ------------------------------------------------------------------
# Handlers
# ------------------------------------------------------------------

def _h_search(g: GraphPort, a: dict[str, Any]) -> str:
    return g.sparql(queries.fts(a["query"], a.get("limit", 10)))


def _h_get_artikel(g: GraphPort, a: dict[str, Any]) -> str:
    return g.sparql(queries.get_artikel(a["bwb_id"], a["artikel"]))


def _h_get_lid(g: GraphPort, a: dict[str, Any]) -> str:
    return g.sparql(queries.get_lid(a["bwb_id"], a["artikel"], a["lid"]))


def _h_get_bepaling(g: GraphPort, a: dict[str, Any]) -> str:
    return g.sparql(queries.get_bepaling(a["bwb_id"], a["nummer"]))


def _h_list_regelingen(g: GraphPort, a: dict[str, Any]) -> str:
    return g.sparql(queries.list_regelingen())


def _h_regeling_info(g: GraphPort, a: dict[str, Any]) -> str:
    return g.sparql(queries.get_regeling_info(a["bwb_id"]))


def _h_verwijzingen(g: GraphPort, a: dict[str, Any]) -> str:
    return g.sparql(queries.follow_verwijzingen(a["bwb_id"], a["artikel"], a.get("lid")))


def _h_context(g: GraphPort, a: dict[str, Any]) -> str:
    return g.sparql(queries.context(a["bwb_id"], a["artikel"], a.get("lid")))


def _h_referenced_by(g: GraphPort, a: dict[str, Any]) -> str:
    return g.sparql(queries.referenced_by(a["bwb_id"], a["artikel"]))


def _h_resolve_begrip(g: GraphPort, a: dict[str, Any]) -> str:
    return g.sparql(queries.resolve_begrip(a["term"]))


def _h_schema(g: GraphPort, a: dict[str, Any]) -> str:
    return schema.graph_schema(g)


def _h_raw_sparql(g: GraphPort, a: dict[str, Any]) -> str:
    return g.sparql(a["query"])


def _h_semantic_search(g: GraphPort, a: dict[str, Any], settings: Any) -> str:
    if settings is None or not getattr(settings, "similarity_index", ""):
        return (
            "Semantisch zoeken is nog niet geconfigureerd (geen similarity-index). "
            "Gebruik search_wetgeving voor tekstueel zoeken."
        )
    try:
        limit = int(a.get("limit", 10))
    except (TypeError, ValueError):
        limit = 10
    limit = max(1, min(50, limit))  # clamp zoals search_wetgeving (kosten/DoS begrenzen)
    return g.semantic_search(a["query"], limit)


# ------------------------------------------------------------------
# Tool-definities
# ------------------------------------------------------------------

_BWB = {"type": "string", "description": "BWB-id van de regeling, bijv. 'BWBR0004770'."}
_ART = {"type": "string", "description": "Artikelnummer, bijv. '9' of '9a'."}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_wetgeving",
        "description": (
            "Full-text zoeken in alle wetteksten (Lucene). Gebruik dit om bepalingen "
            "te vinden als je de vindplaats nog niet kent. Geeft treffers met label en "
            "tekstfragment. Lucene-syntax: AND/OR/NOT, \"exacte frase\", wildcard*."
        ),
        "input_schema": _obj(
            {
                "query": {"type": "string", "description": "Zoekterm(en) in Lucene-syntax."},
                "limit": {"type": "integer", "description": "Max. aantal treffers (1-50, default 10)."},
            },
            ["query"],
        ),
        "handler": _h_search,
    },
    {
        "name": "semantic_search",
        "description": (
            "Semantisch (op betekenis) zoeken met vector-embeddings. Gebruik dit als de gebruiker "
            "een situatie omschrijft of andere woorden gebruikt dan de wettekst; search_wetgeving "
            "is voor exacte termen. Combineer beide bij twijfel (hybride)."
        ),
        "input_schema": _obj(
            {
                "query": {"type": "string", "description": "Natuurlijke omschrijving van wat je zoekt."},
                "limit": {"type": "integer", "description": "Max. aantal treffers (default 10)."},
            },
            ["query"],
        ),
        "handler": _h_semantic_search,
        "needs_settings": True,
    },
    {
        "name": "get_artikel",
        "description": "Haal de tekst, jci-vindplaats en alle leden van één artikel op.",
        "input_schema": _obj({"bwb_id": _BWB, "artikel": _ART}, ["bwb_id", "artikel"]),
        "handler": _h_get_artikel,
    },
    {
        "name": "get_lid",
        "description": "Haal de tekst en vindplaats van één specifiek lid van een artikel op.",
        "input_schema": _obj(
            {"bwb_id": _BWB, "artikel": _ART, "lid": {"type": "string", "description": "Lidnummer, bijv. '1'."}},
            ["bwb_id", "artikel", "lid"],
        ),
        "handler": _h_get_lid,
    },
    {
        "name": "get_bepaling",
        "description": (
            "Haal een bepaling op via haar NUMMER binnen een regeling — werkt voor artikelen ('9', "
            "'25', '22a') én voor beleidsregels/circulaires met decimale nummers zoals '9.1' (bv. de "
            "Leidraad Invordering 2008), waar get_artikel/get_lid niet passen."
        ),
        "input_schema": _obj(
            {"bwb_id": _BWB, "nummer": {"type": "string", "description": "Bepaling-nummer, bijv. '9.1' of '22a'."}},
            ["bwb_id", "nummer"],
        ),
        "handler": _h_get_bepaling,
    },
    {
        "name": "list_regelingen",
        "description": "Geef alle regelingen in de kennisgraaf (citeertitel + soort).",
        "input_schema": _obj({}, []),
        "handler": _h_list_regelingen,
    },
    {
        "name": "get_regeling_info",
        "description": (
            "Metadata van één regeling: citeertitel, opschrift, soort (wet/regeling/"
            "beleidsregel), geldigheid, uitgevende organisatie en ondertekenaar."
        ),
        "input_schema": _obj({"bwb_id": _BWB}, ["bwb_id"]),
        "handler": _h_regeling_info,
    },
    {
        "name": "follow_verwijzingen",
        "description": (
            "Geef de uitgaande verwijzingen vanuit een artikel (of lid): ankertekst, "
            "doel en soort (intref/extref/tekstueel). Voor het volgen van kruisverwijzingen."
        ),
        "input_schema": _obj(
            {"bwb_id": _BWB, "artikel": _ART, "lid": {"type": "string", "description": "Optioneel lidnummer."}},
            ["bwb_id", "artikel"],
        ),
        "handler": _h_verwijzingen,
    },
    {
        "name": "referenced_by",
        "description": "Geef de regelingen die naar dit artikel verwijzen (verwijzingDoor).",
        "input_schema": _obj({"bwb_id": _BWB, "artikel": _ART}, ["bwb_id", "artikel"]),
        "handler": _h_referenced_by,
    },
    {
        "name": "get_context",
        "description": (
            "GraphRAG: haal een bepaling met haar volledige structurele context in één keer "
            "op — de bevattende delen (hoofdstuk/afdeling/regeling), de leden, de uitgaande "
            "verwijzingen én wie naar het artikel verwijst. Gebruik dit voor context- en "
            "verwijzingsvragen i.p.v. losse tools te combineren."
        ),
        "input_schema": _obj(
            {"bwb_id": _BWB, "artikel": _ART, "lid": {"type": "string", "description": "Optioneel lidnummer."}},
            ["bwb_id", "artikel"],
        ),
        "handler": _h_context,
    },
    {
        "name": "resolve_begrip",
        "description": (
            "Zoek een juridisch begrip in de SKOS-thesaurus op label en geef het "
            "concept-IRI plus gerelateerde begrippen."
        ),
        "input_schema": _obj({"term": {"type": "string", "description": "Begrip of deel ervan."}}, ["term"]),
        "handler": _h_resolve_begrip,
    },
    {
        "name": "graph_schema",
        "description": (
            "Geef de live omvang van de graaf (aantallen per type) en de lijst regelingen. "
            "Gebruik dit bij twijfel over wat er in de graaf zit."
        ),
        "input_schema": _obj({}, []),
        "handler": _h_schema,
    },
    {
        "name": "raw_sparql",
        "description": (
            "LAATSTE REDMIDDEL: voer een eigen read-only SPARQL-query (SELECT/CONSTRUCT/"
            "DESCRIBE) uit als geen enkele andere tool volstaat. Updates worden geweigerd."
        ),
        "input_schema": _obj({"query": {"type": "string", "description": "SPARQL SELECT/CONSTRUCT/DESCRIBE."}}, ["query"]),
        "handler": _h_raw_sparql,
    },
]

_BY_NAME: dict[str, dict[str, Any]] = {t["name"]: t for t in TOOLS}


def anthropic_schemas(only: set[str] | frozenset[str] | None = None) -> list[dict[str, Any]]:
    """Model-facing tool-schema's; filter op een toegestane set (None = alle)."""
    return [
        {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
        for t in TOOLS
        if only is None or t["name"] in only
    ]


def dispatch(name: str, graph: GraphPort, args: dict[str, Any] | None, settings: Any = None) -> str:
    tool = _BY_NAME.get(name)
    if tool is None:
        return f"Onbekende tool: {name}"
    try:
        if tool.get("needs_settings"):
            return tool["handler"](graph, args or {}, settings)
        return tool["handler"](graph, args or {})
    except (ValueError, MCPError, KeyError) as exc:
        # Verwachte fouten (ongeldig argument, MCP-fout, ontbrekende sleutel): als tekst teruggeven.
        return f"Fout bij tool '{name}': {exc}"
    except httpx.HTTPError as exc:
        # Transport-/statusfout naar de graaf (timeout, connection-reset): NIET de hele beurt breken —
        # geef 'm als tool-resultaat terug zodat de agent kan herstellen/rapporteren.
        logger.warning("tool '%s' netwerkfout naar de graaf", name, exc_info=True)
        return f"Fout bij tool '{name}': de kennisgraaf was tijdelijk onbereikbaar ({type(exc).__name__})."
    except Exception as exc:  # noqa: BLE001 — vangnet: nooit de agent-beurt laten crashen op een tool
        logger.error("tool '%s' onverwachte fout", name, exc_info=True)
        return f"Fout bij tool '{name}': {exc}"
