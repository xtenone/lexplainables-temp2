#!/usr/bin/env python3
"""Bouw model.json uit de gevalideerde regelspraak-tussenresultaten.

Leest de hoogste ronde van de stappen `gegevensspraak` en `regels` uit de werkmap en
combineert die tot één model.json — de primaire bron voor de HTML-viewer en de
RegelSpraak-tekstexport (.rs/.md). Schrijft standaard ook de tekstexport ernaast.

De drie vrije-tekstvelden (reviewlog GegevensSpraak, reviewlog regels, validatiepunten)
kunnen als vlag worden meegegeven zodat de skill ze in één aanroep invult. Ontbreken ze,
dan blijven ze leeg als startpunt dat de analist later bijwerkt.

Geen dependencies buiten de standaardbibliotheek.

Gebruik:
    python build_regelspraak.py \\
        --werk <pad/naar/regelspraak/werk> \\
        --out  <pad/naar/model.json> \\
        [--reviewlog-gegevensspraak "tekst..."] \\
        [--reviewlog-regels        "tekst..."] \\
        [--validatiepunten         "tekst..."] \\
        [--geen-export]
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Canonieke volgorde van de GegevensSpraak-declaraties in de tekstexport.
GS_VOLGORDE = [
    "eenheidssystemen", "domeinen", "dimensies", "tijdlijnen", "dagsoorten",
    "objecttypen", "feittypen", "parameters",
]


# --- helpers ------------------------------------------------------------------

def laatste_ronde(stap_dir: Path) -> Path | None:
    if not stap_dir.is_dir():
        return None
    rondes = []
    for p in stap_dir.glob("ronde-*"):
        m = re.fullmatch(r"ronde-(\d+)", p.name)
        if m and p.is_dir():
            rondes.append((int(m.group(1)), p))
    if not rondes:
        return None
    return max(rondes, key=lambda t: t[0])[1]


def laad_json(pad: Path) -> dict:
    try:
        return json.loads(pad.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        sys.exit(f"FOUT: kan {pad} niet lezen: {e}")


def verzamel_rondes(stap_dir: Path) -> list[dict]:
    """Leesbare reviewlog-context per ronde (status, items, algemeen)."""
    if not stap_dir.is_dir():
        return []
    out = []
    for p in sorted(
        stap_dir.glob("ronde-*"),
        key=lambda q: int(re.fullmatch(r"ronde-(\d+)", q.name).group(1))
        if re.fullmatch(r"ronde-(\d+)", q.name) else 0,
    ):
        m = re.fullmatch(r"ronde-(\d+)", p.name)
        if not (m and p.is_dir()):
            continue
        fb = None
        fb_pad = p / "feedback.json"
        if fb_pad.exists():
            try:
                fb = json.loads(fb_pad.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        out.append({
            "ronde": int(m.group(1)),
            "items": (fb or {}).get("items") or {},
            "algemeen": ((fb or {}).get("algemeen") or "").strip(),
            "status": (fb or {}).get("status", ""),
        })
    return out


# --- tekstexport (.rs / .md) --------------------------------------------------

def render_rs(model: dict) -> str:
    """Render de letterlijke RegelSpraak-tekst (GegevensSpraak-declaraties + regels)."""
    blokken: list[str] = []
    gs = model.get("gegevensspraak") or {}
    for sleutel in GS_VOLGORDE:
        for decl in (gs.get(sleutel) or []):
            tekst = (decl.get("regelspraak_tekst") or "").strip()
            if tekst:
                blokken.append(tekst)
    for r in (model.get("regels") or []):
        tekst = (r.get("regelspraak_tekst") or "").strip()
        if tekst:
            blokken.append(tekst)
    return "\n\n".join(blokken) + "\n"


def render_md(model: dict) -> str:
    wg = model.get("werkgebied") or {}
    titel = wg.get("naam") or "werkgebied"
    regels = [
        f"# RegelSpraak-specificatie — {titel}",
        "",
        "> Formalisering volgens de RegelSpraak-specificatie v2.3.0 (Belastingdienst/ALEF).",
        "> Concept als hulpmiddel — bedoeld voor multidisciplinaire validatie (jurist,",
        "> informatieanalist, ICT). Interpretatiekeuzes zijn als zodanig gemarkeerd.",
        "",
        "## 0. Werkgebied en afbakening",
        "",
        f"- **Werkgebied:** {wg.get('naam', '')}",
        f"- **Afbakening (scoping):** {wg.get('scoping', '')}",
        f"- **Bron-rapport:** {wg.get('bron_rapport') or '—'}",
        "",
        "## 1. GegevensSpraak (objectmodel)",
        "",
        "```regelspraak",
    ]
    gs = model.get("gegevensspraak") or {}
    for sleutel in GS_VOLGORDE:
        for decl in (gs.get(sleutel) or []):
            tekst = (decl.get("regelspraak_tekst") or "").strip()
            if tekst:
                regels.append(tekst)
                regels.append("")
    regels += ["```", "", "## 2. RegelSpraak-regels", "", "```regelspraak"]
    for r in (model.get("regels") or []):
        tekst = (r.get("regelspraak_tekst") or "").strip()
        if tekst:
            regels.append(tekst)
            regels.append("")
    regels += ["```", "", "## 3. Reviewlog en aandachtspunten", ""]
    regels.append(f"- **GegevensSpraak:** {model.get('reviewlog_gegevensspraak') or '_TODO_'}")
    regels.append(f"- **Regels:** {model.get('reviewlog_regels') or '_TODO_'}")
    regels += ["", "### Aandachtspunten voor validatie", ""]
    vp = model.get("validatiepunten") or []
    if isinstance(vp, str):
        vp = [vp] if vp.strip() else []
    if vp:
        for v in vp:
            regels.append(f"- {v}")
    else:
        regels.append("_TODO_")
    regels.append("")
    return "\n".join(regels) + "\n"


def slug(model: dict) -> str:
    naam = (model.get("werkgebied") or {}).get("naam") or ""
    s = re.sub(r"[^a-z0-9]+", "-", naam.lower()).strip("-")
    return s or "regelspraak"


# --- main ---------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--werk", required=True, type=Path,
                    help="werkmap met gegevensspraak/ en regels/")
    ap.add_argument("--out", required=True, type=Path, help="pad naar het te schrijven model.json")
    ap.add_argument("--reviewlog-gegevensspraak", default="",
                    help="prozasamenvatting reviewlog stap GegevensSpraak")
    ap.add_argument("--reviewlog-regels", default="",
                    help="prozasamenvatting reviewlog stap regels")
    ap.add_argument("--validatiepunten", default="",
                    help="aandachtspunten voor validatie (regels gescheiden door newline)")
    ap.add_argument("--geen-export", action="store_true",
                    help="schrijf geen .rs/.md-tekstexport naast model.json")
    args = ap.parse_args()

    dir_gs = args.werk / "gegevensspraak"
    dir_regels = args.werk / "regels"

    ronde_gs = laatste_ronde(dir_gs)
    ronde_regels = laatste_ronde(dir_regels)
    if ronde_gs is None:
        sys.exit(f"FOUT: geen ronde gevonden in {dir_gs}")
    if ronde_regels is None:
        sys.exit(f"FOUT: geen ronde gevonden in {dir_regels}")

    m_gs = laad_json(ronde_gs / "model.json")
    m_regels = laad_json(ronde_regels / "model.json")

    werkgebied = dict(m_gs.get("werkgebied") or m_regels.get("werkgebied") or {})
    validatiepunten = m_regels.get("validatiepunten") or []
    if isinstance(validatiepunten, str):
        validatiepunten = [validatiepunten] if validatiepunten.strip() else []
    if args.validatiepunten.strip():
        validatiepunten = [r.strip() for r in args.validatiepunten.split("\n") if r.strip()]

    model = {
        "werkgebied": werkgebied,
        "gegevensspraak": m_gs.get("gegevensspraak") or {},
        "regels": m_regels.get("regels") or [],
        "reviewlog_gegevensspraak": args.reviewlog_gegevensspraak.strip(),
        "reviewlog_regels": args.reviewlog_regels.strip(),
        "validatiepunten": validatiepunten,
        "reviewlog": {
            "gegevensspraak": {"rondes": verzamel_rondes(dir_gs)},
            "regels": {"rondes": verzamel_rondes(dir_regels)},
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")

    n_decl = sum(len(model["gegevensspraak"].get(k) or []) for k in GS_VOLGORDE)
    print(f"model.json geschreven naar {args.out}")
    print(f"Bron: gegevensspraak {ronde_gs.name}, regels {ronde_regels.name} "
          f"({n_decl} declaratie(s), {len(model['regels'])} regel(s))")

    if not args.geen_export:
        basis = args.out.parent / slug(model)
        rs_pad = basis.with_suffix(".rs")
        md_pad = basis.with_suffix(".md")
        rs_pad.write_text(render_rs(model), encoding="utf-8")
        md_pad.write_text(render_md(model), encoding="utf-8")
        print(f"Tekstexport: {rs_pad.name}, {md_pad.name}")

    leeg = sum([
        1 if not model["reviewlog_gegevensspraak"] else 0,
        1 if not model["reviewlog_regels"] else 0,
        1 if not model["validatiepunten"] else 0,
    ])
    if leeg:
        print(f"Let op: {leeg} vrij tekstveld(en) nog leeg "
              "(--reviewlog-gegevensspraak, --reviewlog-regels, --validatiepunten).")


if __name__ == "__main__":
    main()
