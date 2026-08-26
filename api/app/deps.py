"""Dependency-wiring. De jobstore is altijd beschikbaar; de engine vereist LLM-config
en wordt lui gebouwd zodat read/serve zonder LiteLLM draait."""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache

from .config import get_settings
from .jobstore import JobStore
from .postgres_store import PostgresStore
from .wettenbank import WettenbankClient

logger = logging.getLogger(__name__)

_tasks: set[asyncio.Task] = set()


def _on_done(task: asyncio.Task) -> None:
    _tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        # Achtergrondtaken vangen hun eigen faalklassen via _guard af; komt er tóch een
        # exceptie hier uit, dan is die ongezien — log 'm i.p.v. stil te verliezen.
        logger.error("Achtergrondtaak faalde: %s", exc, exc_info=exc)


def schedule(coro) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_on_done)


async def drain_tasks(timeout: float = 10.0) -> None:
    """Bij een nette shutdown: annuleer en wacht kort op nog lopende achtergrond-analyses i.p.v.
    ze hard af te kappen. Best-effort — een geannuleerde analyse laat zijn lease verlopen en wordt
    door de reaper hersteld (job → fout, herstelbaar via retry). De timeout voorkomt dat een
    hangende taak de shutdown blokkeert."""
    taken = [t for t in _tasks if not t.done()]
    if not taken:
        return
    for t in taken:
        t.cancel()
    try:
        await asyncio.wait_for(
            asyncio.gather(*taken, return_exceptions=True), timeout
        )
    except asyncio.TimeoutError:
        logger.warning("Niet alle achtergrondtaken stopten binnen %ss bij shutdown.", timeout)


@lru_cache
def get_store() -> JobStore:
    return PostgresStore(get_settings())


@lru_cache
def get_annotatie_store() -> "AnnotatieStore":
    from .annotatie_store import AnnotatieStore

    return AnnotatieStore()


@lru_cache
def get_wettenbank() -> WettenbankClient:
    return WettenbankClient(get_settings())


@lru_cache
def get_engine():
    from .engine.orchestrator import WetsanalyseEngine

    settings = get_settings()
    # Geen vaste LLM-client meer: de engine resolveert per analyse het modelprofiel (uit de store) en
    # bouwt de adapter dan pas. Zo pakt het runtime-beheer (admin-UI) wijzigingen direct op.
    return WetsanalyseEngine(settings, get_store(), None, get_wettenbank())
