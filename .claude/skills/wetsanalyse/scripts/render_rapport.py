#!/usr/bin/env python3
"""Rapportgenerator voor de wetsanalyse-skill.

Rendert de deterministische delen van het eindrapport (secties 0-2 en het
reviewlog-skelet) rechtstreeks uit de gevalideerde `analyse.json`-bestanden van
de laatste reviewronde. Zo hoeft de skill de letterlijke wettekst en markeringen
niet zelf over te typen — dat scheelt tokens en garandeert dat sectie 1-2
brongetrouw met de bron overeenkomt.

Wat dit script NIET doet (dat blijft mensen-/skillwerk, want het is synthese):
- de §3-aandachtspunten voor multidisciplinaire validatie (de 5 categorieën);
- de prozasamenvatting "wat is per ronde gewijzigd" in de reviewlog.
Het script levert daarvoor een skelet met het ruwe materiaal (twijfelvelden,
feedback per ronde) onder een `_TODO_`-markering, zodat de skill het gericht afmaakt.

Geen dependencies buiten de standaardbibliotheek.

Gebruik:
    python render_rapport.py \
        --werk <pad/naar/analyse/werk> \
        --out  <pad/naar/analyserapport.md>

`--werk` is de werkmap met `activiteit-2/ronde-*/`. Het script kiest automatisch
de hoogste ronde.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_analyse import jas_sorteersleutel  # noqa: E402 — sibling-script, zelfde map

TODO = "_TODO_"


# --- inlezen --------------------------------------------------------------

def laatste_ronde(activiteit_dir: Path) -> Path | None:
    """Geef de map `ronde-N` met de hoogste N binnen een activiteitmap."""
    if not activiteit_dir.is_dir():
        return None
    rondes = []
    for p in activiteit_dir.glob("ronde-*"):
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


def verzamel_rondes(activiteit_dir: Path) -> list[tuple[int, dict | None]]:
    """Geef per ronde (oplopend) de feedback.json, of None als die ontbreekt."""
    if not activiteit_dir.is_dir():
        return []
    out = []
    for p in sorted(activiteit_dir.glob("ronde-*"),
                    key=lambda q: int(re.fullmatch(r"ronde-(\d+)", q.name).group(1))
                    if re.fullmatch(r"ronde-(\d+)", q.name) else 0):
        m = re.fullmatch(r"ronde-(\d+)", p.name)
        if not (m and p.is_dir()):
            continue
        fb_pad = p / "feedback.json"
        fb = None
        if fb_pad.exists():
            try:
                fb = json.loads(fb_pad.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                fb = None
        out.append((int(m.group(1)), fb))
    return out


# --- helpers voor markdown ------------------------------------------------

def cel(tekst: str | None) -> str:
    """Maak tekst veilig voor een markdown-tabelcel (pipes/newlines)."""
    if not tekst:
        return ""
    return str(tekst).replace("|", "\\|").replace("\n", "<br>").strip()


def veld(data: dict, sleutel: str) -> str:
    """Haal een veld op of geef de TODO-markering als het ontbreekt/leeg is."""
    waarde = data.get(sleutel)
    if waarde is None or str(waarde).strip() == "":
        return TODO
    return str(waarde).strip()


# --- rendering ------------------------------------------------------------

def bron_titel(b: dict) -> str:
    if b.get("label"):
        return b["label"]
    if b.get("wet"):
        lid = f" lid {b['lid']}" if b.get("lid") else ""
        return f"{b['wet']} art. {b.get('artikel', '')}{lid}"
    return b.get("bron_id", "bron")


def lid_suffix(label: str, lid) -> str:
    """Lid-suffix voor een vindplaats. Normaliseert de lid-waarde (strip een eventuele
    `lid `-prefix, zodat zowel "1" als "lid 1" op "1" uitkomt) en laat de suffix weg als het
    bron-label het lid al bevat (bron op lid-niveau) of als er geen lid is (lid-loos artikel)."""
    s = re.sub(r"^\s*lid\s+", "", str(lid or "").strip(), flags=re.IGNORECASE)
    if not s or label.rstrip().lower().endswith(f"lid {s}".lower()):
        return ""
    return f" lid {s}"


def vindplaats_text(vps, bron_label: dict) -> str:
    if not isinstance(vps, list) or not vps:
        return ""
    delen = []
    for vp in vps:
        lbl = bron_label.get(vp.get("bron_id"), vp.get("bron_id", ""))
        delen.append(lbl + lid_suffix(lbl, vp.get("lid")))
    return "; ".join(d for d in delen if d)


def titel(a2: dict) -> str:
    wg = a2.get("werkgebied") or {}
    bronnen = a2.get("bronnen") or []
    naam = wg.get("naam") or (bron_titel(bronnen[0]) if len(bronnen) == 1 else "werkgebied")
    return f"# Wetsanalyse — {naam}"


def sectie_0(a2: dict) -> list[str]:
    wg = a2.get("werkgebied") or {}
    bronnen = a2.get("bronnen") or []
    regels = [
        "## 0. Werkgebied en afbakening",
        "",
        f"- **Werkgebied:** {wg.get('naam', TODO)}",
        f"- **Hoofdvraag / analysefocus:** {wg.get('hoofdvraag') or wg.get('analysefocus') or TODO}",
        f"- **Omschrijving:** {wg.get('omschrijving') or TODO}",
        f"- **Afbakening (scoping):** {wg.get('scoping') or TODO}",
        "",
        f"### Bronnen in het werkgebied ({len(bronnen)})",
        "",
    ]
    for b in bronnen:
        det = " · ".join(x for x in [b.get("bwbId"), b.get("versiedatum"), b.get("bronreferentie")] if x)
        regels.append(f"- **{bron_titel(b)}** — {det}")
    regels.append("")
    return regels


def sectie_bronnen(a2: dict) -> list[str]:
    """§1/§2 per bron: wettekst, markeringen, verwijzingen, samenhang."""
    regels = ["## 1/2. Bronnen — wettekst, markeringen en verwijzingen", ""]
    for i, b in enumerate(a2.get("bronnen") or [], 1):
        regels += [f"### Bron {i} — {bron_titel(b)}", "", "**Wettekst (letterlijk)**", ""]
        for lid in b.get("leden", []):
            regels.append(f"**Lid {lid.get('lid', '?')}.** {lid.get('tekst', TODO)}")
            regels.append("")
        regels += [
            "**Markeringen en classificaties**",
            "",
            "| # | Formulering (letterlijk) | JAS-klasse | Vindplaats | Toelichting |",
            "| --- | --- | --- | --- | --- |",
        ]
        for m in sorted(b.get("markeringen", []),
                        key=lambda m: jas_sorteersleutel(m.get("klasse", ""))):
            regels.append(
                f"| {cel(m.get('id'))} | \"{cel(m.get('formulering'))}\" | "
                f"{cel(m.get('klasse'))} | {cel(m.get('vindplaats'))} | {cel(m.get('toelichting'))} |"
            )
        verwijzingen = b.get("verwijzingen", [])
        if verwijzingen:
            regels += ["", "**Verwijzingen**", "",
                       "| # | Functie | Doel | Bron | Soort | Status | Betekenis |",
                       "| --- | --- | --- | --- | --- | --- | --- |"]
            for v in verwijzingen:
                doel = v.get("doel") or {}
                doel_tekst = doel.get("label") or doel.get("target") or ""
                regels.append(
                    f"| {cel(v.get('id'))} | {cel(v.get('functie'))} | {cel(doel_tekst)} | "
                    f"{cel(v.get('bron_lid'))} | {cel(v.get('soort'))} | {cel(v.get('status'))} | "
                    f"{cel(v.get('betekenis'))} |"
                )
        if b.get("samenhang"):
            regels += ["", f"**Samenhang:** {b['samenhang']}"]
        regels.append("")
    return regels


def reviewlog_regel(naam: str, rondes: list[tuple[int, dict | None]]) -> list[str]:
    if not rondes:
        return [f"- **{naam}:** {TODO} (geen rondes gevonden)"]
    laatste = rondes[-1][1]
    akkoord_schoon = (
        laatste
        and laatste.get("status") == "akkoord"
        and not laatste.get("items")
        and not (laatste.get("algemeen") or "").strip()
    )
    if len(rondes) == 1 and akkoord_schoon:
        return [f"- **{naam}:** 1 ronde — de analist ging in ronde 1 meteen akkoord, "
                "zonder per-item- of algemene feedback. Geen wijzigingen doorgevoerd."]
    # Meerdere rondes of feedback: skelet met ruw materiaal voor de skill.
    out = [f"- **{naam}:** {len(rondes)} ronde(s) — {TODO} vat per ronde samen wat op grond "
           "van de feedback is gewijzigd. Ruw materiaal per ronde:"]
    for n, fb in rondes:
        if fb is None:
            out.append(f"  - ronde {n}: (geen feedback.json)")
            continue
        items = fb.get("items") or {}
        algemeen = (fb.get("algemeen") or "").strip()
        if fb.get("status") == "akkoord" and not items and not algemeen:
            out.append(f"  - ronde {n}: akkoord zonder opmerkingen.")
            continue
        delen = []
        for k, v in items.items():
            delen.append(f"[{k}] {v}")
        if algemeen:
            delen.append(f"[algemeen] {algemeen}")
        out.append(f"  - ronde {n}: " + " · ".join(delen))
    return out


def sectie_3(rondes2) -> list[str]:
    regels = ["## 3. Reviewlog en aandachtspunten voor validatie", "", "### Reviewlog", ""]
    regels += reviewlog_regel("Activiteit 2", rondes2)
    regels += [
        "",
        "### Aandachtspunten voor multidisciplinaire validatie",
        "",
        f"> {TODO} — De skill vult dit gestructureerd in (interpretatiekeuzes / open normen /",
        "> openstaande delegaties / aannames / buiten scope), op basis van de twijfelvelden",
        "> in de markeringen. Verwijder dit blok na invullen.",
        "",
    ]
    return regels


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--werk", required=True, type=Path,
                    help="werkmap met activiteit-2/")
    ap.add_argument("--out", required=True, type=Path, help="pad naar het rapport (.md)")
    args = ap.parse_args()

    dir2 = args.werk / "activiteit-2"

    ronde2 = laatste_ronde(dir2)
    if ronde2 is None:
        sys.exit(f"FOUT: geen ronde gevonden in {dir2}")

    a2 = laad_json(ronde2 / "analyse.json")
    rondes2 = verzamel_rondes(dir2)

    regels: list[str] = [
        titel(a2),
        "",
        "> Analyse volgens de methode Wetsanalyse (Ausems, Bulles & Lokin), activiteit 2.",
        "> Dit is een **concept-analyse als hulpmiddel**: bedoeld voor multidisciplinaire validatie",
        "> (jurist, informatieanalist, ICT). Interpretatiekeuzes zijn als zodanig gemarkeerd.",
        "",
    ]
    regels += sectie_0(a2)
    regels += sectie_bronnen(a2)
    regels += sectie_3(rondes2)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(regels) + "\n", encoding="utf-8")

    aantal_todo = ("\n".join(regels)).count(TODO)
    print(f"Rapport geschreven naar {args.out}")
    print(f"Bron: activiteit-2 {ronde2.name}")
    if aantal_todo:
        print(f"Let op: {aantal_todo}× {TODO} — vul deze handmatig/in de skill aan "
              "(sectie 0-metadata en de §3-aandachtspunten).")


if __name__ == "__main__":
    main()
