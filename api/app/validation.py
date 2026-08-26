"""Canonieke JAS-klassenlijst — de enige bron voor de klassevalidatie in het annotatiedomein.

`GELDIGE_JAS_KLASSEN` komt uit het skill-script `validate_analyse.py` (de gedeelde
`references`/`scripts`-inhoudsbron), zodat de api niet drift ten opzichte van het skill-spoor. Het
annotatiedomein (`routers/annotatie.py`) valideert de klasse van een voorgesteld element hiertegen.

> De vroegere brongetrouwheid-/schema-checks van de (verwijderde) `/v1/projects`-analyse-pijplijn
> stonden hier ook; die zijn weg. Brongetrouwheid wordt nu afgedwongen in graph-qa (grounding) en de
> frontend (`segmenteer`), niet server-side in de api.
"""

from __future__ import annotations

import importlib.util
import sys

from .config import SKILL_SCRIPTS


def _load_module_from(scripts_dir, naam: str):
    """Laad een skill-script als module (de scripts vormen geen package)."""
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    pad = scripts_dir / f"{naam}.py"
    spec = importlib.util.spec_from_file_location(naam, pad)
    if spec is None or spec.loader is None:
        raise ImportError(f"Kan skill-script niet laden: {pad}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_skill_module(naam: str):
    return _load_module_from(SKILL_SCRIPTS, naam)


_validate = _load_skill_module("validate_analyse")

# Alles hieronder komt uit dezelfde canonieke bron (drift-fix). Naast de validatie-set heeft de
# export de weergave-volgorde en de labelkleuren van de JAS-tabel nodig; die horen dus ook hier
# vandaan te komen en niet uit een tweede lijstje in de exportmodule.
GELDIGE_JAS_KLASSEN: set[str] = _validate.GELDIGE_JAS_KLASSEN
JAS_KLASSEN_VOLGORDE: tuple[str, ...] = _validate.JAS_KLASSEN_VOLGORDE
JAS_KLASSE_KLEUREN: dict[str, tuple[str, str]] = _validate.JAS_KLASSE_KLEUREN
JAS_TEKSTKLEUR: str = _validate.JAS_TEKSTKLEUR
jas_sorteersleutel = _validate.jas_sorteersleutel
