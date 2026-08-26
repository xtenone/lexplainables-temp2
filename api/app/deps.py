"""Dependency-wiring. De API bedient het annotatie-domein van de werkplek, het login-/
gebruikersbeheer en het LLM-modelprofielbeheer; de annotatie-store is de enige gewirede
afhankelijkheid (de werkplek haalt wettekst rechtstreeks uit de graaf via graph-qa)."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .annotatie_store import AnnotatieStore
    from .gesprek_store import GesprekStore

logger = logging.getLogger(__name__)


@lru_cache
def get_annotatie_store() -> "AnnotatieStore":
    from .annotatie_store import AnnotatieStore

    return AnnotatieStore()


@lru_cache
def get_gesprek_store() -> "GesprekStore":
    from .gesprek_store import GesprekStore

    return GesprekStore()
