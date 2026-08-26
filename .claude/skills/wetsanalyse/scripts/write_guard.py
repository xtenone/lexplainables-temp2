#!/usr/bin/env python3
"""Pre-tool-use hook: blokkeert schrijfacties naar beschermde analyse-bestanden.

Geldt voor beide sporen onder analyses/ (wetsanalyse → analyse.json; regelspraak → model.json):
  1. analyses/**/werk/**/feedback.json          — alleen de review-server schrijft dit; nooit de skill.
  2. analyses/**/werk/**/(analyse|model).json   — immutabel zodra de ronde VOLTOOID is, d.w.z.
     zodra feedback.json in dezelfde ronde-map bestaat. Correcties vóór de review (bv. na een
     validate-fout, verplicht volgens SKILL.md) blijven toegestaan; overschrijven ná feedback niet.

Ontvangt via stdin: {"tool_name": "...", "tool_input": {"file_path": "..."}}
Exit 0: toegestaan; exit 2: geblokkeerd (stderr-bericht zichtbaar voor de skill/analist).

Configureer als PreToolUse hook in .claude/settings.json (matcher: "Write|Edit").
"""

import json
import re
import sys
from pathlib import Path

# Beide patronen matchen een willekeurige werk/-boom onder analyses/ — dus ook de geneste
# regelspraak-werkmap (analyses/<wg>/regelspraak/werk/...) naast de wetsanalyse-werkmap.
_FEEDBACK = re.compile(
    r"[/\\]analyses[/\\].+[/\\]werk[/\\].+[/\\]feedback\.json$",
    re.IGNORECASE,
)
_ANALYSE = re.compile(
    r"[/\\]analyses[/\\].+[/\\]werk[/\\].+[/\\](analyse|model)\.json$",
    re.IGNORECASE,
)


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, OSError):
        sys.exit(0)

    file_path = str((data.get("tool_input") or {}).get("file_path") or "")
    if not file_path:
        sys.exit(0)

    if _FEEDBACK.search(file_path):
        print(
            f"GEBLOKKEERD: {file_path}\n"
            "feedback.json wordt uitsluitend door de review-server geschreven. "
            "Pas de review aan via de webpagina.",
            file=sys.stderr,
        )
        sys.exit(2)

    if _ANALYSE.search(file_path):
        # Een ronde-resultaat (analyse.json/model.json) in werk/ wordt immutabel zodra de ronde
        # VOLTOOID is — dat is het moment waarop feedback.json in de ronde-map verschijnt (alleen
        # de review-server schrijft die). Vóór dat moment mag de skill het bestand corrigeren
        # (SKILL.md verplicht herstel van validatiefouten binnen dezelfde ronde); daarna is
        # overschrijven het herschrijven van een gereviewde ronde en dus geblokkeerd.
        doel = Path(file_path)
        if doel.is_file() and (doel.parent / "feedback.json").is_file():
            print(
                f"GEBLOKKEERD: {file_path}\n"
                "Deze ronde is al gereviewd (feedback.json bestaat) en daarmee immutabel. "
                "Schrijf naar een nieuwe ronde (ronde-N+1) in plaats van de bestaande te overschrijven.",
                file=sys.stderr,
            )
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
