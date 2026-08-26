"""Drift-guard: de JAS-labelkleuren staan op twee plekken en moeten identiek blijven.

De canonieke bron is het skill-script (`validate_analyse.py`), waar de api ze via `validation.py`
uit leest voor de PDF-export. De werkplek draagt dezelfde waarden als Tailwind-klassen in
`frontend/lib/jas.ts`, want een browser kan dat Python-bestand niet lezen. Twee kopieën van
dezelfde kleuren driften zonder toets — vandaar deze test.
"""
from __future__ import annotations

import re

import pytest

from app.config import PROJECT_ROOT
from app.validation import GELDIGE_JAS_KLASSEN, JAS_KLASSE_KLEUREN, JAS_KLASSEN_VOLGORDE

JAS_TS = PROJECT_ROOT / "frontend" / "lib" / "jas.ts"

# `Klasse: "bg-[#xxxxxx] text-ink border-[#yyyyyy]"` — met of zonder aanhalingstekens om de sleutel.
REGEL = re.compile(
    r'^\s*"?([A-Za-z][^":]*?)"?:\s*"bg-\[(#[0-9a-fA-F]{6})\][^"]*border-\[(#[0-9a-fA-F]{6})\]"',
    re.MULTILINE,
)


def _kleuren_uit_frontend() -> dict[str, tuple[str, str]]:
    bron = JAS_TS.read_text(encoding="utf-8")
    return {m.group(1): (m.group(2).lower(), m.group(3).lower()) for m in REGEL.finditer(bron)}


def test_kleurmap_dekt_precies_de_dertien_klassen():
    assert set(JAS_KLASSE_KLEUREN) == GELDIGE_JAS_KLASSEN
    assert len(JAS_KLASSEN_VOLGORDE) == 13


@pytest.mark.skipif(not JAS_TS.exists(), reason="frontend niet aanwezig (api-only image)")
def test_frontend_draagt_dezelfde_kleuren():
    fe = _kleuren_uit_frontend()
    canoniek = {k: (bg.lower(), rand.lower()) for k, (bg, rand) in JAS_KLASSE_KLEUREN.items()}
    assert fe == canoniek, (
        "frontend/lib/jas.ts wijkt af van de canonieke kleuren in de skill "
        "(.claude/skills/wetsanalyse/scripts/validate_analyse.py)"
    )
