"""LLM-kostenrem/robuustheid: globale concurrency-limiter (throttle), de pre-flight
prompt-token-guard, prompt-caching-telemetrie en de repareer-retry binnen één `complete()`-call."""

import asyncio

import pytest

from app.llm import throttle


# --- #1 concurrency-limiter ---

async def test_llm_slot_begrenst_gelijktijdigheid():
    throttle.configure(2)
    try:
        actief = piek = 0

        async def taak():
            nonlocal actief, piek
            async with throttle.llm_slot():
                actief += 1
                piek = max(piek, actief)
                await asyncio.sleep(0.01)
                actief -= 1

        await asyncio.gather(*(taak() for _ in range(6)))
        assert piek <= 2  # nooit meer dan het plafond tegelijk
    finally:
        throttle.configure(0)


async def test_llm_slot_uit_is_noop():
    throttle.configure(0)
    async with throttle.llm_slot():
        pass  # geen rem, geen blokkade


# --- #2 context-window: pre-flight token-guard ---

def test_prompt_guard_werpt_bij_overschrijding():
    from app.llm.base import LlmConfig, PromptTooLargeError
    from app.llm.litellm_client import LiteLLMClient

    client = LiteLLMClient(LlmConfig(model="gpt-test", max_prompt_tokens=10))
    with pytest.raises(PromptTooLargeError):
        # ~250 tokens via de chars/4-fallback ≫ cap 10.
        client._guard_prompt([{"role": "user", "content": "x" * 1000}])


def test_prompt_guard_laat_klein_door_en_noop_zonder_limiet():
    from app.llm.base import LlmConfig
    from app.llm.litellm_client import LiteLLMClient

    # Onder de cap → geen fout.
    LiteLLMClient(LlmConfig(model="gpt-test", max_prompt_tokens=100000))._guard_prompt(
        [{"role": "user", "content": "kort"}]
    )
    # Geen cap + onbekend model → geen afleidbare limiet → geen fout, ongeacht grootte.
    LiteLLMClient(LlmConfig(model="onbekend-model-zzz", max_prompt_tokens=0))._guard_prompt(
        [{"role": "user", "content": "x" * 100000}]
    )


# --- #3 repareer-retry binnen één complete()-call: usage telt beide beurten ---

async def test_repair_retry_telt_usage_van_beide_calls(monkeypatch):
    """Faalt de eerste generatie op JSON en herstelt de repareer-retry het, dan telt de
    LLMResult de tokens van BEIDE calls — de eerste (mislukte) generatie is óók verbruik.

    litellm zit in de optionele `llm`-extra en ontbreekt in de CI-testomgeving; de client
    importeert het pas ín complete(), dus een stub-module in sys.modules volstaat en de test
    draait overal (de token-fallback vangt het ontbrekende token_counter-attribuut op)."""
    import sys
    import types

    from app.llm.base import LlmConfig
    from app.llm.litellm_client import LiteLLMClient

    class _Usage:
        def __init__(self, i, o):
            self.prompt_tokens = i
            self.completion_tokens = o

    class _Msg:
        def __init__(self, c):
            self.content = c

    class _Choice:
        def __init__(self, c):
            self.message = _Msg(c)

    class _Resp:
        def __init__(self, c, i, o):
            self.choices = [_Choice(c)]
            self.usage = _Usage(i, o)
            self.model = "fake/model"

    responsen = iter([
        _Resp("dit is geen json", 10, 5),          # eerste poging: onparseerbaar
        _Resp('{"ok": true}', 20, 7),              # repareer-retry: geldig
    ])

    async def fake_acompletion(**kwargs):
        return next(responsen)

    stub = types.ModuleType("litellm")
    stub.acompletion = fake_acompletion
    monkeypatch.setitem(sys.modules, "litellm", stub)
    client = LiteLLMClient(LlmConfig(model="fake/model", max_prompt_tokens=1_000_000))
    res = await client.complete("sys", "user")

    assert res.data == {"ok": True}
    assert res.tokens_in == 30   # 10 + 20
    assert res.tokens_out == 12  # 5 + 7


# --- #5 prompt caching: cachebaar system-blok + cache-token-telemetrie ---

def test_system_message_cachebaar_blok_aan_en_uit():
    from app.llm.base import LlmConfig
    from app.llm.litellm_client import LiteLLMClient

    aan = LiteLLMClient(LlmConfig(model="m", prompt_caching=True))._system_message("REF")
    assert aan["content"] == [{"type": "text", "text": "REF", "cache_control": {"type": "ephemeral"}}]

    uit = LiteLLMClient(LlmConfig(model="m", prompt_caching=False))._system_message("REF")
    assert uit == {"role": "system", "content": "REF"}


def test_cache_tokens_leest_usage_defensief():
    from app.llm.litellm_client import LiteLLMClient

    class Usage:  # provider-stijl usage-object
        cache_read_input_tokens = 1200
        cache_creation_input_tokens = 800

    assert LiteLLMClient._cache_tokens(Usage()) == (1200, 800)
    assert LiteLLMClient._cache_tokens(None) == (0, 0)

    class Nested:  # alternatieve vorm: genest onder prompt_tokens_details
        cache_read_input_tokens = 0
        cache_creation_input_tokens = 0
        class prompt_tokens_details:  # noqa: N801
            cached_tokens = 512

    assert LiteLLMClient._cache_tokens(Nested()) == (512, 0)
