"""Generieke runtime-instellingen (key/value) bovenop de store.

Dunne service rond `JobStore.lees_app_setting`/`schrijf_app_setting` met een korte in-proces
TTL-cache, zodat een vaak-gelezen toggle (zoals `capture_llm_calls`, gelezen bij élke LLM-call)
niet telkens een DB-hit kost. De cache wordt bij een set meteen ververst.

Bewust een aparte module (vgl. profiles/wetten): de instellingen zijn DB-backed en
runtime-beheerbaar via /v1/admin/settings + het /beheer-scherm, los van de env-`Settings`.
"""

from __future__ import annotations

import time

from .jobstore import JobStore

CAPTURE_LLM_CALLS = "capture_llm_calls"

# Korte cache: (waarde, vervaltijd) per sleutel. TTL bewust kort — een toggle moet snel doorwerken.
_TTL_S = 10.0
_cache: dict[str, tuple[object, float]] = {}


def _nu() -> float:
    return time.monotonic()


async def lees(store: JobStore, key: str, default=None):
    """Lees een instelling met TTL-cache; valt terug op `default` als de sleutel ontbreekt."""
    treffer = _cache.get(key)
    if treffer is not None and treffer[1] > _nu():
        return treffer[0]
    waarde = await store.lees_app_setting(key)
    if waarde is None:
        waarde = default
    _cache[key] = (waarde, _nu() + _TTL_S)
    return waarde


async def schrijf(store: JobStore, key: str, value) -> None:
    """Persisteer een instelling en ververs de cache meteen."""
    await store.schrijf_app_setting(key, value)
    _cache[key] = (value, _nu() + _TTL_S)


async def capture_enabled(store: JobStore) -> bool:
    """Staat het vastleggen van LLM-calls aan? Default uit (opt-in via /beheer)."""
    return bool(await lees(store, CAPTURE_LLM_CALLS, default=False))


async def set_capture(store: JobStore, aan: bool) -> None:
    await schrijf(store, CAPTURE_LLM_CALLS, bool(aan))


def _wis_cache() -> None:
    """Alleen voor tests: maak de in-proces cache leeg."""
    _cache.clear()
