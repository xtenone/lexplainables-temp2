"""Capture-wrapper rond een LLMClient: legt de feitelijke prompt + ruwe respons vast.

Wraps elke `complete()`-call en persisteert — als de runtime-toggle `capture_llm_calls` aan staat —
één `llm_calls`-rij met `system`/`user`-prompt en de ruwe respons, plus metadata. Vangt óók
gefaalde calls (`ok=false` + error) en de auto-correctie-herhalingen, omdat die juist interessant
zijn voor prompt-/gedragsanalyse.

De call-context (project/activiteit/ronde/poging/fase) ligt niet in de `complete`-signature (die is
vastgelegd door het Protocol), dus die komt uit een `ContextVar` die de orchestrator rond de
generatie zet. Capture is **best-effort**: een fout in het vastleggen mag de analyse nooit breken.
"""

from __future__ import annotations

import contextlib
import contextvars
import logging

from ..app_settings import capture_enabled
from ..jobstore import JobStore
from .base import LLMClient, LLMResult

logger = logging.getLogger(__name__)

# Per-async-task call-context; default leeg. De orchestrator vult 'm via gebruik_context().
llm_call_ctx: contextvars.ContextVar[dict] = contextvars.ContextVar("llm_call_ctx", default={})


@contextlib.contextmanager
def gebruik_context(**velden):
    """Zet de call-context voor de duur van het blok (gemerged met de huidige) en herstel daarna."""
    huidig = dict(llm_call_ctx.get() or {})
    huidig.update({k: v for k, v in velden.items() if v is not None})
    token = llm_call_ctx.set(huidig)
    try:
        yield
    finally:
        llm_call_ctx.reset(token)


def werk_context_bij(**velden) -> None:
    """Werk losse velden in de huidige call-context bij (bv. `poging`/`fase` in de auto-correctie-lus)."""
    huidig = dict(llm_call_ctx.get() or {})
    huidig.update({k: v for k, v in velden.items() if v is not None})
    llm_call_ctx.set(huidig)


class CapturingLLMClient:
    """LLMClient-decorator die elke call best-effort vastlegt. Passthrough als capture uit staat."""

    def __init__(self, inner: LLMClient, store: JobStore) -> None:
        self._inner = inner
        self._store = store

    async def complete(self, system: str, user: str, schema: dict | None = None) -> LLMResult:
        try:
            res = await self._inner.complete(system, user, schema)
        except Exception as e:  # noqa: BLE001 — leg de gefaalde call vast en geef de fout door
            await self._leg_vast(system, user, res=None, ok=False, error=repr(e))
            raise
        await self._leg_vast(system, user, res=res, ok=True, error=None)
        return res

    async def _leg_vast(self, system: str, user: str, res: LLMResult | None, ok: bool, error: str | None) -> None:
        try:
            if not await capture_enabled(self._store):
                return
            ctx = llm_call_ctx.get() or {}
            await self._store.schrijf_llm_call({
                "project_slug": ctx.get("project_slug", ""),
                "activiteit": ctx.get("activiteit", ""),
                "ronde": ctx.get("ronde", 0),
                "poging": ctx.get("poging", 1),
                "fase": ctx.get("fase", ""),
                "model": (res.model if res else "") or ctx.get("model", ""),
                "provider": res.provider if res else "",
                "system_prompt": system,
                "user_prompt": user,
                "response_text": res.ruwe_tekst if res else "",
                "tokens_in": res.tokens_in if res else 0,
                "tokens_out": res.tokens_out if res else 0,
                "ok": ok,
                "error": error,
            })
        except Exception:  # noqa: BLE001 — capture is best-effort, nooit de analyse breken
            logger.warning("LLM-call-capture mislukt (genegeerd)", exc_info=True)
