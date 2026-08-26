"""Globale concurrency-rem op LLM-calls (kostenbeheersing tegen zelf-veroorzaakte rate-limits).

Een proces-globale semafoor begrenst hoeveel LLM-calls er TEGELIJK lopen over alle analyses heen.
Zonder deze rem knallen veel gelijktijdige analyses samen tegen de provider-quota → een zwerm 429's.
Per proces (in-process); bij >1 replica is de effectieve grens `replicas × max_concurrency`.

De semafoor wordt bij startup geconfigureerd (`configure`, vanuit de lifespan) zodat de grootte uit
Settings komt; tests configureren 'm rechtstreeks. Niet ingesteld of 0 → geen rem (yield direct).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

_sem: asyncio.Semaphore | None = None


def configure(max_concurrency: int) -> None:
    """(Her)initialiseer de globale semafoor. <= 0 schakelt de rem uit."""
    global _sem
    _sem = asyncio.Semaphore(max_concurrency) if max_concurrency and max_concurrency > 0 else None


@asynccontextmanager
async def llm_slot():
    """Reserveer één concurrency-slot voor de duur van een LLM-completion. Zonder rem: no-op."""
    if _sem is None:
        yield
        return
    async with _sem:
        yield
