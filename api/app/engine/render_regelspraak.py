"""Tekstexport van het regelspraak-model (.rs / .md) — hergebruikt de skill-renderer.

De API schrijft niet naar disk; deze module levert de RegelSpraak-tekst en Markdown als string voor
de export-endpoints. Om drift met het skill-spoor te voorkomen lenen we `render_rs`/`render_md`
rechtstreeks uit `build_regelspraak.py` (zelfde canonieke volgorde + opmaak).
"""

from __future__ import annotations

from ..validation import _load_module_from
from ..config import REGELSPRAAK_SCRIPTS

_build = _load_module_from(REGELSPRAAK_SCRIPTS, "build_regelspraak")


def render_rs(model: dict) -> str:
    return _build.render_rs(model)


def render_md(model: dict) -> str:
    return _build.render_md(model)
