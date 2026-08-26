"""Kleine helpers gedeeld door de wrapper (agent.py) en de orkestrator."""
from __future__ import annotations

import asyncio


class BeurtGestopt(Exception):
    """De jurist heeft om stoppen gevraagd; de graaf hoort geen nieuwe node meer te betreden.

    Bewust een exception en géén `task.cancel()`. De nodes zijn synchroon en draaien in de
    default-executor: een `run_in_executor`-future is niet annuleerbaar, en de MCP-verbinding wordt
    in een `finally` gesloten — die onder een nog draaiende thread wegtrekken breekt hem. Dit stopt
    dus netjes op een nodegrens, met een consistente checkpointer-state.

    Gevolg voor de gebruiker: stoppen kost tijd, want de lopende stap (een LLM- of MCP-call) maakt
    zichzelf eerst af. Dat hoort de UI te tonen in plaats van te doen alsof het meteen klaar is.
    """


def truncate(text: str, max_chars: int = 8000) -> str:
    if len(text) > max_chars:
        return text[:max_chars] + f"\n...[resultaat ingekort op {max_chars} tekens]"
    return text


async def run_sync(fn, *args):
    """Draai een blocking functie in de default executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn, *args)
