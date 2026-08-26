"""Fakes voor de poorten, zodat de agent-loop deterministisch en zonder netwerk test."""
from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from agent.config import Settings


def make_settings(**kw: Any) -> Settings:
    """Settings voor tests: in-memory checkpointer (geen db-file) tenzij overschreven."""
    kw.setdefault("checkpoint_db_path", None)
    return Settings(**kw)


# ---- LLM-response bouwstenen (vorm van de Anthropic-response) ----

def text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def tool_block(id: str, name: str, input: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=id, name=name, input=input)


def response(content: list[SimpleNamespace], stop_reason: str) -> SimpleNamespace:
    return SimpleNamespace(content=content, stop_reason=stop_reason)


class _FakeStream:
    """Streamt de tekstblokken van één response als deltas (LLMStream-protocol)."""

    def __init__(self, resp: SimpleNamespace) -> None:
        self._resp = resp

    def __enter__(self) -> "_FakeStream":
        return self

    def __exit__(self, *_exc: Any) -> bool:
        return False

    @property
    def text_deltas(self):
        text = "".join(b.text for b in self._resp.content if b.type == "text")
        for i in range(0, len(text), 12):  # in brokjes, als een echte stream
            yield text[i:i + 12]

    def final_message(self) -> SimpleNamespace:
        return self._resp


class FakeLLM:
    """Speelt een vaste reeks responses af via create() én stream() (gedeelde index)."""

    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self._responses = list(responses)
        self.index = 0
        self.calls: list[dict[str, Any]] = []

    def _next(self) -> SimpleNamespace:
        resp = self._responses[self.index]
        self.index += 1
        return resp

    def _leg_vast(self, kwargs: dict[str, Any]) -> None:
        """Onthoud de call, met `system` als één string.

        De aanroeper mag het systeemblok gesplitst aanleveren (`[stabiel, variabel]`) zodat de echte
        adapter er een prompt-cache-punt tussen kan zetten; wat het model uiteindelijk leest is de
        aaneenschakeling. Tests vragen naar dát — de splitsing zelf staat in `system_delen`.
        """
        systeem = kwargs.get("system")
        if isinstance(systeem, list):
            kwargs = {**kwargs, "system_delen": systeem, "system": "\n\n".join(d for d in systeem if d)}
        self.calls.append(kwargs)

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self._leg_vast(kwargs)
        return self._next()

    def stream(self, **kwargs: Any) -> _FakeStream:
        self._leg_vast(kwargs)
        return _FakeStream(self._next())


class FakeGraph:
    """GraphPort-fake: onthoudt de uitgevoerde SPARQL en geeft canned tekst terug."""

    def __init__(
        self,
        result: str = "",
        results: Callable[[str], str] | None = None,
    ) -> None:
        self._result = result
        self._results = results
        self.queries: list[str] = []
        self.semantic_queries: list[str] = []
        self.closed = False

    def initialize(self) -> dict[str, Any]:
        return {}

    def sparql(self, query: str) -> str:
        self.queries.append(query)
        if self._results is not None:
            return self._results(query)
        return self._result

    def semantic_search(self, query: str, limit: int = 10) -> str:
        self.semantic_queries.append(query)
        return self._result

    def close(self) -> None:
        self.closed = True
