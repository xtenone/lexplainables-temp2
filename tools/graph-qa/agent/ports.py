"""
Poorten (Protocols) die de agent-loop scheiden van concrete providers.

De loop praat uitsluitend via deze interfaces, zodat tests een fake kunnen
injecteren zonder netwerk, en zodat een tweede LLM-/graaf-provider later een
kwestie van een nieuwe adapter is.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class GraphPort(Protocol):
    """Toegang tot de kennisgraaf via de MCP-server (of een fake).

    De domeintools bouwen SPARQL en voeren die uit via sparql(); de loop hoeft
    het rauwe MCP-tooloppervlak niet te kennen.
    """

    def initialize(self) -> dict[str, Any]: ...

    def sparql(self, query: str) -> str:
        """Voer een read-only SPARQL-query uit en geef de resultaattekst terug."""
        ...

    def semantic_search(self, query: str, limit: int = 10) -> str:
        """Semantisch (vector) zoeken via de embedding-connector; resultaattekst."""
        ...

    def close(self) -> None: ...


# Het systeemblok van één call. Eén string is het gewone geval; een reeks strings zegt: alles
# behalve het laatste deel is STABIEL over calls heen, en daar mag de provider een prompt-cache op
# zetten. De volgorde is dus betekenisdragend — caching is een prefix-match, dus één byte verschil
# vóór het cache-punt maakt de hele cache waardeloos.
Systeem = str | list[str]


@runtime_checkable
class LLMPort(Protocol):
    """Eén blocking chat-completion met tool-use.

    Retourneert het provider-native response-object (blokken met .type/.text/
    .id/.name/.input en een .stop_reason); de loop leest daar direct uit, en een
    fake kan hetzelfde vormpje teruggeven.
    """

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        system: Systeem,
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> Any: ...

    def stream(
        self,
        *,
        model: str,
        max_tokens: int,
        system: Systeem,
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> "LLMStream":
        """Als create(), maar streamend. Gebruik als context manager."""
        ...


@runtime_checkable
class LLMStream(Protocol):
    """Context manager over één streamende completion.

    `text_deltas` levert de tekst-brokjes zodra ze binnenkomen; `final_message()`
    geeft na afloop het volledige response-object (blokken + stop_reason).
    """

    def __enter__(self) -> "LLMStream": ...

    def __exit__(self, *exc: Any) -> bool | None: ...

    @property
    def text_deltas(self) -> Iterator[str]: ...

    def final_message(self) -> Any: ...
