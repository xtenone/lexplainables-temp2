"""
MCP HTTP client voor de GraphDB MCP-server.

Implementeert het MCP Streamable HTTP transport protocol:
  - POST /mcp  voor initialize / tools/list / tools/call
  - Authorization: Bearer *** server stuurt initialize als plain JSON,
overige calls als SSE (text/event-stream) die direct sluit na het eerste event.
Gebruik httpx.post() (geen streaming) — de server sluit de verbinding zelf.

Eén persistente httpx.Client wordt hergebruikt over alle calls (connection pooling;
scheelt een TCP+TLS-handshake per tool-aanroep). close() sluit die client af.

Veiligheidsnet: call_tool weigert SPARQL-argumenten die eruitzien als een update
(INSERT/DELETE/LOAD/CLEAR/DROP/CREATE). De echte read-only-garantie hoort aan de
serverkant; dit is defense-in-depth zolang het model nog rauwe SPARQL kan sturen.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx


class MCPError(Exception):
    pass


# Allowlist in plaats van blocklist. De vorige opzet zocht naar update-sleutelwoorden, en dat is
# een spel dat je niet wint: `LOAD`/`CLEAR`/`DROP` werden alleen aan het BEGIN van een regel
# herkend, dus `PREFIX x: <http://a/> LOAD <http://evil/x.ttl>` liep er zo doorheen. Nu is de vraag
# omgedraaid — wat overblijft na het strippen van commentaar, PREFIX en BASE moet met een
# lees-vorm beginnen. Alles wat daar niet aan voldoet wordt geweigerd, ook wat we nog niet kennen.
_LEESVORMEN = ("select", "ask", "construct", "describe")

# Commentaar tot regeleinde — maar niet elk '#' begint commentaar: een stringliteral kan er een
# bevatten ("nr. #3") en vrijwel elke prefix-IRI eindigt erop (<urn:bwb-ns:>). Beide
# vormen matchen daarom éérst, zodat alleen een echt losstaand '#' als commentaar wordt gestript.
_STRING_OF_HASH = re.compile(r'"(?:[^"\\]|\\.)*"' r"|'(?:[^'\\]|\\.)*'" r"|<[^>\s]*>" r"|#[^\n]*")
# Een PREFIX-/BASE-declaratie vooraan; herhaald strippen tot de eigenlijke query overblijft.
_DECLARATIE_RE = re.compile(
    r"^\s*(?:base\s*<[^>]*>|prefix\s+[^\s:]*:\s*<[^>]*>)\s*", re.IGNORECASE
)


def _query_kern(query: str) -> str:
    """De query zonder commentaar en zonder PREFIX-/BASE-declaraties — wat er echt wordt uitgevoerd."""
    zonder_commentaar = _STRING_OF_HASH.sub(lambda m: "" if m.group(0).startswith("#") else m.group(0), query or "")
    kern = zonder_commentaar.lstrip()
    while True:
        nieuw = _DECLARATIE_RE.sub("", kern, count=1)
        if nieuw == kern:
            return kern.lstrip()
        kern = nieuw.lstrip()


def _looks_like_update(query: str) -> bool:
    """True voor alles wat geen leesquery is — inclusief een lege of onherkenbare query.

    Bewust streng: het GraphDB-service-account achter de auth-proxy mág schrijven op de repository,
    dus dit vangnet is in de praktijk wat een schrijf-SPARQL vanuit de agent tegenhoudt. Bij twijfel
    weigeren kost hooguit een tool-foutmelding die het model kan herstellen; doorlaten kan de graaf
    kosten.
    """
    kern = _query_kern(query).lower()
    return not kern.startswith(_LEESVORMEN)


def _content_to_text(content: list[Any]) -> str:
    """Plat een MCP-content-lijst tot één tekst."""
    parts = []
    for item in content:
        if isinstance(item, dict):
            parts.append(item.get("text", str(item)))
        else:
            parts.append(str(item))
    return "\n".join(parts)


class MCPClient:
    """Dunne synchrone client voor de GraphDB MCP-server."""

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        repository_id: str | None = None,
        sparql_tool: str = "sparql_query",
        similarity_index: str = "",
    ) -> None:
        self.url = (url or os.environ["GRAPHDB_MCP_URL"]).rstrip("/")
        token = token or os.environ["GRAPHDB_TOKEN"]
        self._auth_header = f"Bearer {token}"
        self._repository_id = repository_id or os.environ.get("GRAPHDB_REPOSITORY_ID", "inning")
        self._sparql_tool = sparql_tool
        self._similarity_index = similarity_index
        self._session_id: str | None = None
        self._client = httpx.Client(
            timeout=httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0),
        )

    # ------------------------------------------------------------------
    # Intern: JSON-RPC over MCP HTTP
    # ------------------------------------------------------------------

    def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
        }
        if params:
            payload["params"] = params

        headers = {
            "Authorization": self._auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        resp = self._client.post(self.url, json=payload, headers=headers)

        # Sla session-id op
        sid = resp.headers.get("Mcp-Session-Id")
        if sid:
            self._session_id = sid

        if resp.status_code == 202:
            return None

        ct = resp.headers.get("content-type", "")

        if "text/event-stream" in ct:
            return self._parse_sse_body(resp.text)
        else:
            try:
                data = resp.json()
            except Exception as exc:
                raise MCPError(
                    f"Geen geldige JSON van MCP-server (HTTP {resp.status_code}): {resp.text[:200]}"
                ) from exc
            if "error" in data:
                raise MCPError(f"MCP-fout: {data['error']}")
            # Non-2xx zonder JSON-RPC-result → expliciet falen i.p.v. stil een leeg resultaat teruggeven.
            if resp.status_code >= 400 and "result" not in data:
                raise MCPError(f"MCP HTTP {resp.status_code}: {resp.text[:200]}")
            return data.get("result")

    @staticmethod
    def _parse_sse_body(text: str) -> Any:
        """Haal het eerste JSON-RPC result-object uit een SSE-response body."""
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if "result" in msg:
                return msg["result"]
            if "error" in msg:
                raise MCPError(f"MCP-fout (SSE): {msg['error']}")
        raise MCPError(f"Geen bruikbaar resultaat in SSE-response: {text[:200]}")

    # ------------------------------------------------------------------
    # Publieke interface
    # ------------------------------------------------------------------

    def initialize(self) -> dict[str, Any]:
        """Handshake met de MCP-server; retourneert server-capabilities."""
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "graph-qa", "version": "0.1.0"},
            },
        )
        # notifications/initialized is optioneel; GraphDB hangt bij die call.
        return result or {}

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._rpc("tools/list")
        if result is None:
            return []
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        if result is None:
            return []
        return result.get("content", [])

    def sparql(self, query: str) -> str:
        """Voer een read-only SPARQL-query uit via de MCP-sparql-tool.

        De read-only guard hoort hier — op de SPARQL-string — en niet in het generieke `call_tool`:
        anders zou hij ook de natuurlijke-taal-query van `similarity_search` scannen en die onterecht
        weigeren zodra ze met een verb begint of iets als 'delete where' bevat."""
        self._reject_updates({"query": query})
        content = self.call_tool(
            self._sparql_tool,
            {"query": query, "repositoryId": self._repository_id},
        )
        return _content_to_text(content)

    def semantic_search(self, query: str, limit: int = 10) -> str:
        """Semantisch zoeken via de GraphDB-similarity-index (MCP-tool similarity_search)."""
        content = self.call_tool(
            "similarity_search",
            {
                "query": query,
                "similarityIndex": self._similarity_index,
                "connectorType": "similarity",
                "repositoryId": self._repository_id,
                "limit": limit,
            },
        )
        return _content_to_text(content)

    @staticmethod
    def _reject_updates(arguments: dict[str, Any]) -> None:
        """Weiger argumenten die een SPARQL-update bevatten (read-only vangnet)."""
        for value in arguments.values():
            if isinstance(value, str) and _looks_like_update(value):
                raise MCPError(
                    "Geweigerd: alleen read-only SPARQL is toegestaan "
                    "(update-sleutelwoord aangetroffen)."
                )

    def close(self) -> None:
        # Idempotent en best-effort: bij een SSE-client-disconnect kan `close()` samenvallen met een
        # nog lopende call in een executor-thread; laat het sluiten daar niet op stuklopen.
        try:
            self._client.close()
        except Exception:  # noqa: BLE001 — sluiten mag nooit de afhandeling breken
            pass

    def __enter__(self) -> "MCPClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
