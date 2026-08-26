"""LiteLLM-implementatie van LLMClient.

Provider-prefix/auth komen uit de meegegeven `LlmConfig` (afgeleid uit een modelprofiel of de
env-fallback; Azure-endpointtype vastgesteld in Fase 0: `azure_ai/...` voor Foundry/MaaS,
`azure/...` voor Azure OpenAI). De echte JSON-garantie is niet de provider-feature maar deze
laag: schema verbatim in de prompt → parse → één gerichte repareer-retry → de caller valideert
tegen Pydantic.
"""

from __future__ import annotations

import json

from .base import LlmConfig, LLMError, LLMResult, PromptTooLargeError, parse_json_strict
from .throttle import llm_slot

_REPAREER = (
    "Je vorige antwoord was geen geldige JSON. Geef UITSLUITEND geldig JSON terug dat exact "
    "voldoet aan het gevraagde schema. Geen uitleg, geen markdown-fences."
)


class LiteLLMClient:
    def __init__(self, config: LlmConfig) -> None:
        self.c = config
        if not config.model:
            raise RuntimeError("LLM-model niet geconfigureerd (leeg in profiel én env).")

    def _model_ref(self) -> str:
        # LiteLLM verwacht "<provider>/<model>" tenzij het model al een prefix bevat.
        model = self.c.model
        if "/" in model:
            return model
        return f"{self.c.provider}/{model}"

    def _kwargs(self) -> dict:
        kw: dict = {"temperature": self.c.temperature}
        if self.c.api_base:
            kw["api_base"] = self.c.api_base
        if self.c.api_key:
            kw["api_key"] = self.c.api_key
        if self.c.api_version:  # alleen Azure OpenAI
            kw["api_version"] = self.c.api_version
        if self.c.timeout:  # 0 = geen expliciete timeout (laat de provider-default staan)
            kw["timeout"] = self.c.timeout
        # json_object-strategie: laat de provider geldig JSON afdwingen waar dat kan.
        if self.c.output_strategy == "json_object":
            kw["response_format"] = {"type": "json_object"}
        return kw

    def _prompt_limiet(self) -> int | None:
        """Max prompt-tokens: de expliciete cap, anders auto uit het model (95% van de
        max_input_tokens). Onbekend model → None (geen limiet, geen vals-positief)."""
        if self.c.max_prompt_tokens > 0:
            return self.c.max_prompt_tokens
        try:
            import litellm
            info = litellm.get_model_info(self._model_ref())
            mx = info.get("max_input_tokens") if info else None
            if mx:
                return int(mx * 0.95)
        except Exception:  # noqa: BLE001 — onbekend model/uitval → geen limiet afdwingen
            pass
        return None

    def _system_message(self, system: str) -> dict:
        """Bouw het system-bericht. Met caching aan wordt het als één cachebaar content-block
        gestuurd (`cache_control: ephemeral`): de references vormen per fase een byte-stabiele
        prefix, dus volgende bronnen/rondes lezen 'm uit de cache i.p.v. opnieuw te betalen."""
        if self.c.prompt_caching:
            return {
                "role": "system",
                "content": [
                    {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
                ],
            }
        return {"role": "system", "content": system}

    @staticmethod
    def _cache_tokens(usage) -> tuple[int, int]:
        """Lees cache-read/-write prompt-tokens defensief uit de provider-`usage` (vorm verschilt
        per provider; ontbreekt → 0,0). Nooit een telemetrie-detail de call laten breken."""
        if usage is None:
            return 0, 0
        read = getattr(usage, "cache_read_input_tokens", 0) or 0
        write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        if not read:  # sommige providers nesten het onder prompt_tokens_details
            details = getattr(usage, "prompt_tokens_details", None)
            read = (getattr(details, "cached_tokens", 0) or 0) if details else 0
        return int(read), int(write)

    def _tel_tokens(self, messages: list[dict]) -> int:
        """Model-bewuste token-telling; valt terug op een grove heuristiek (chars/4)."""
        try:
            import litellm
            return litellm.token_counter(model=self._model_ref(), messages=messages)
        except Exception:  # noqa: BLE001
            return sum(len(m.get("content", "")) for m in messages) // 4

    def _guard_prompt(self, messages: list[dict]) -> None:
        lim = self._prompt_limiet()
        if lim is None:
            return
        n = self._tel_tokens(messages)
        if n > lim:
            raise PromptTooLargeError(
                f"Prompt ~{n} tokens > limiet {lim} voor model {self.c.model}; verklein het "
                "werkgebied (minder bronnen) of kies een modelprofiel met een groter context window."
            )

    async def complete(self, system: str, user: str, schema: dict | None = None) -> LLMResult:
        import litellm

        schema_hint = ""
        if schema is not None:
            schema_hint = (
                "\n\nGeef je antwoord als JSON dat exact voldoet aan dit schema:\n"
                + json.dumps(schema, ensure_ascii=False, indent=2)
            )
        messages = [
            self._system_message(system),
            {"role": "user", "content": user + schema_hint},
        ]

        # Pre-flight: faal snel en duidelijk als de prompt het context window overschrijdt,
        # i.p.v. een rauwe provider-400 (en zonder die zinloos te retryen).
        self._guard_prompt(messages)

        # Eén completion (incl. de evt. repareer-retry) telt als één concurrency-slot: zo houdt de
        # globale rem het aantal gelijktijdige LLM-calls onder het plafond, ongeacht de repair.
        try:
            async with llm_slot():
                resp = await litellm.acompletion(model=self._model_ref(), messages=messages, **self._kwargs())
                tekst = resp.choices[0].message.content or ""
                usage = getattr(resp, "usage", None)
                tokens_in = getattr(usage, "prompt_tokens", 0) or 0
                tokens_out = getattr(usage, "completion_tokens", 0) or 0

                try:
                    data = parse_json_strict(tekst)
                except json.JSONDecodeError:
                    # Eén gerichte repareer-retry. De tokens ervan tellen mee: de eerste
                    # (mislukte) generatie is óók verbruikt (budget/usage-aggregatie).
                    messages.append({"role": "assistant", "content": tekst})
                    messages.append({"role": "user", "content": _REPAREER})
                    resp = await litellm.acompletion(model=self._model_ref(), messages=messages, **self._kwargs())
                    tekst = resp.choices[0].message.content or ""
                    usage = getattr(resp, "usage", None)
                    tokens_in += getattr(usage, "prompt_tokens", 0) or 0
                    tokens_out += getattr(usage, "completion_tokens", 0) or 0
                    try:
                        data = parse_json_strict(tekst)
                    except json.JSONDecodeError as e:
                        raise LLMError(f"Geen geldige JSON na reparatie: {e}") from e
        except Exception as e:  # noqa: BLE001 — vertaal een provider-context-overflow naar een duidelijke fout
            if type(e).__name__ == "ContextWindowExceededError":
                raise PromptTooLargeError(
                    f"Context window overschreden voor model {self.c.model}; verklein het werkgebied "
                    "(minder bronnen) of kies een modelprofiel met een groter context window."
                ) from e
            raise

        cache_read, cache_write = self._cache_tokens(usage)
        return LLMResult(
            data=data,
            model=getattr(resp, "model", self.c.model) or self.c.model,
            provider=self.c.provider,
            output_strategie=self.c.output_strategy,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cache_read_in=cache_read,
            cache_write_in=cache_write,
            ruwe_tekst=tekst,
        )


def build_llm_client(config: LlmConfig):
    """Factory — nu LiteLLM; uitbreidbaar naar andere adapters zonder de caller te raken."""
    return LiteLLMClient(config)
