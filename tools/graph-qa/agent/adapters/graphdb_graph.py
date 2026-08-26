"""
GraphPort-adapter voor de GraphDB MCP-server.

De bestaande MCPClient voldoet al aan het GraphPort-protocol; deze factory bouwt er
één uit Settings, inclusief het repository-id en de naam van de SPARQL-tool.
"""
from __future__ import annotations

from ..config import Settings
from ..mcp_client import MCPClient
from ..ports import GraphPort


def make_graph(settings: Settings) -> GraphPort:
    settings.require_graph()
    return MCPClient(
        url=settings.graphdb_mcp_url,
        token=settings.graphdb_token,
        repository_id=settings.repository_id,
        sparql_tool=settings.graphdb_sparql_tool,
        similarity_index=settings.similarity_index,
    )
