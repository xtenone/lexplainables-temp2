"""Rapportbouw — twee varianten:

  bouw_rapport(werk, ...)      — filesystem-variant voor de lokale skill-flow
  bouw_rapport_async(store, ..) — store-variant voor de API (geen filesystem-afhankelijkheid)

We roepen het script NIET als subprocess of via main() aan: dat doet sys.exit() bij fouten en
zou de FastAPI-worker killen.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .validation import _load_skill_module

if TYPE_CHECKING:
    from .jobstore import JobStore

_build = _load_skill_module("build_rapport_json")
laatste_ronde = _build.laatste_ronde
verzamel_rondes = _build.verzamel_rondes
bouw_reviewlog_rondes = _build.bouw_reviewlog_rondes
_laad_json = _build.laad_json


def bouw_rapport(
    werk: Path,
    reviewlog_act2: str = "",
    reviewlog_act3: str = "",
    aandachtspunten: str = "",
) -> dict:
    """Combineer de hoogste ronde van act-2 en act-3 tot één rapport-dict."""
    dir2 = werk / "activiteit-2"
    dir3 = werk / "activiteit-3"
    ronde2 = laatste_ronde(dir2)
    ronde3 = laatste_ronde(dir3)
    if ronde2 is None:
        raise ValueError(f"geen ronde gevonden in {dir2}")
    if ronde3 is None:
        raise ValueError(f"geen ronde gevonden in {dir3}")

    a2 = _laad_json(ronde2 / "analyse.json")
    a3 = _laad_json(ronde3 / "analyse.json")

    werkgebied = dict(a2.get("werkgebied") or {})
    werkgebied.setdefault("analysefocus", a2.get("analysefocus", ""))
    return {
        "werkgebied": werkgebied,
        "bronnen": a2.get("bronnen", []),
        "begrippen": a3.get("begrippen", []),
        "afleidingsregels": a3.get("afleidingsregels", []),
        "validatiepunten": a3.get("validatiepunten", []),
        "reviewlog": {
            "activiteit2": {
                "samenvatting": reviewlog_act2.strip(),
                "rondes": bouw_reviewlog_rondes(verzamel_rondes(dir2)),
            },
            "activiteit3": {
                "samenvatting": reviewlog_act3.strip(),
                "rondes": bouw_reviewlog_rondes(verzamel_rondes(dir3)),
            },
        },
        "aandachtspunten": aandachtspunten.strip(),
    }


async def bouw_rapport_async(
    store: "JobStore",
    job_id: str,
    reviewlog_act2: str = "",
    reviewlog_act3: str = "",
    aandachtspunten: str = "",
) -> dict:
    """Rapportbouw direct uit de jobstore — gebruikt door de API-orchestrator."""
    n2 = await store.hoogste_ronde(job_id, "2")
    n3 = await store.hoogste_ronde(job_id, "3")
    a2 = await store.lees_analyse(job_id, "2", n2) or {}
    a3 = await store.lees_analyse(job_id, "3", n3) or {}
    rondes2 = await store.lees_alle_rondes(job_id, "2")
    rondes3 = await store.lees_alle_rondes(job_id, "3")

    def reviewlog_rondes(rondes: dict) -> list[dict]:
        # Zelfde ronde-vorm als de skill (bouw_reviewlog_rondes), incl. `status` — zo is een
        # `akkoord-afronden`-keuze (act2-only) ook in het API-rapport zichtbaar.
        return bouw_reviewlog_rondes([
            (int(k), rd.feedback)
            for k, rd in sorted(rondes.items(), key=lambda x: int(x[0]))
        ])

    werkgebied = dict(a2.get("werkgebied") or {})
    werkgebied.setdefault("analysefocus", a2.get("analysefocus", ""))
    return {
        "werkgebied": werkgebied,
        "bronnen": a2.get("bronnen", []),
        "begrippen": a3.get("begrippen", []),
        "afleidingsregels": a3.get("afleidingsregels", []),
        "validatiepunten": a3.get("validatiepunten", []),
        "reviewlog": {
            "activiteit2": {"samenvatting": reviewlog_act2.strip(), "rondes": reviewlog_rondes(rondes2)},
            "activiteit3": {"samenvatting": reviewlog_act3.strip(), "rondes": reviewlog_rondes(rondes3)},
        },
        "aandachtspunten": aandachtspunten.strip(),
    }
