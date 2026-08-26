"""Het LLMClient-protocol + resultaattype.

De adapter (niet de caller) kapselt provider-verschillen in: system/user-mapping,
output-strategie en JSON-parsing. De caller geeft een schema en krijgt een dict terug.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


@dataclass
class LlmConfig:
    """Resolved configuratie voor één LLM-call — afgeleid uit een modelprofiel (of env-fallback).

    Maakt de adapter onafhankelijk van Settings: per analyse kan een ander profiel (en dus een
    andere `LlmConfig`) gelden, runtime-beheerbaar via de admin-UI.
    """

    provider: str = "azure_ai"
    model: str = ""
    api_base: str = ""
    api_key: str | None = None
    api_version: str | None = None
    output_strategy: str = "prompt_and_parse"
    temperature: float = 0.0
    # Wandklok-timeout per call in seconden (0 = uit) — doorgegeven aan de provider-call.
    timeout: float = 0.0
    # Harde cap op prompt-tokens (0 = auto-afleiden uit het model; onbekend → geen limiet).
    max_prompt_tokens: int = 0
    # Prompt caching: markeer het (stabiele) system-blok als cachebaar (`cache_control: ephemeral`).
    # De references vormen per fase een byte-stabiele prefix → cache-hit over bronnen/rondes heen.
    # Provider-afhankelijk; bij een provider die het niet ondersteunt zet je deze vlag uit (env
    # WETSANALYSE_LLM_PROMPT_CACHING=0) en valt alles terug op het oude gedrag.
    prompt_caching: bool = True


@dataclass
class LLMResult:
    data: dict
    model: str = ""
    provider: str = ""
    output_strategie: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    # Prompt-cache-telemetrie (provider-afhankelijk; 0 als de provider niet cachet of caching uit staat).
    # cache_read_in = uit de cache geserveerde prompt-tokens (~0.1× kosten); cache_write_in = vers
    # geschreven (~1.25×). `tokens_in` blijft de niet-gecachte rest, conform de provider-`usage`.
    cache_read_in: int = 0
    cache_write_in: int = 0
    ruwe_tekst: str = field(default="", repr=False)


class LLMError(RuntimeError):
    """Het LLM leverde geen bruikbare/parseerbare JSON na een reparatiepoging."""


class PromptTooLargeError(LLMError):
    """De prompt overschrijdt het context window (pre-flight of provider-`ContextWindowExceeded`).

    Erft van LLMError → de orchestrator mapt 'm naar een terminale `fout` (FoutKlasse.llm) met een
    leesbaar bericht. Bewust NIET-transiënt: retryen lost een te grote prompt niet op."""


@runtime_checkable
class LLMClient(Protocol):
    async def complete(self, system: str, user: str, schema: dict | None = None) -> LLMResult:
        """Genereer JSON conform `schema`. Werpt LLMError bij onparseerbaar resultaat."""
        ...


def parse_json_strict(tekst: str) -> dict:
    """Parse JSON; strip defensief code-fences en eventuele preamble vóór het eerste '{'."""
    kandidaat = _FENCE.sub("", tekst.strip())
    try:
        return json.loads(kandidaat)
    except json.JSONDecodeError:
        # Val terug op het grootste {...}-blok.
        start = kandidaat.find("{")
        end = kandidaat.rfind("}")
        if start != -1 and end > start:
            return json.loads(kandidaat[start : end + 1])
        raise
