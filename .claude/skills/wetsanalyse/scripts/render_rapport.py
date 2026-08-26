#!/usr/bin/env python3
"""Rapportgenerator voor de wetsanalyse-skill.

Rendert de deterministische delen van het eindrapport (secties 0-3 en het
reviewlog-skelet) rechtstreeks uit de gevalideerde `analyse.json`-bestanden van
de laatste reviewronde. Zo hoeft de skill de letterlijke wettekst, markeringen,
begrippen en afleidingsregels niet zelf over te typen — dat scheelt tokens en
garandeert dat sectie 1-3 brongetrouw met de bron overeenkomt.

Wat dit script NIET doet (dat blijft mensen-/skillwerk, want het is synthese):
- de §4-aandachtspunten voor multidisciplinaire validatie (de 5 categorieën);
- de prozasamenvatting "wat is per ronde gewijzigd" in de reviewlog.
Het script levert daarvoor een skelet met het ruwe materiaal (validatiepunten,
twijfelvelden, feedback per ronde) onder een `_TODO_`-markering, zodat de skill
het gericht afmaakt.

Geen dependencies buiten de standaardbibliotheek.

Gebruik:
    python render_rapport.py \
        --werk <pad/naar/analyse/werk> \
        --out  <pad/naar/analyserapport.md>

`--werk` is de werkmap met `activiteit-2/ronde-*/` en `activiteit-3/ronde-*/`.
Het script kiest per activiteit automatisch de hoogste ronde.
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


# --- act-3-weergave: begrippen zijn de bouwstenen van regels (id → naam) ---------

def begrip_naam_map(begrippen) -> dict:
    return {b.get("id"): (b.get("naam") or b.get("id") or "")
            for b in (begrippen or []) if b.get("id")}


def begrip_ref(bid, namen: dict) -> str:
    if not bid:
        return ""
    naam = namen.get(bid)
    return f"{naam} ({bid})" if naam and naam != bid else str(bid)


def definitie_text(b: dict) -> str:
    d = b.get("definitie") or ""
    return d + (" [interpretatie]" if d and b.get("is_interpretatie") else "")


def relaties_text(relaties, namen: dict) -> str:
    delen = []
    for r in (relaties or []):
        if not isinstance(r, dict):
            continue
        doel = f" → {begrip_ref(r['doel_begrip'], namen)}" if r.get("doel_begrip") else ""
        soort = f"{r['soort']}: " if r.get("soort") else ""
        delen.append(f"{soort}{r.get('beschrijving', '')}{doel}")
    return "; ".join(d for d in delen if d)


def herkomst_text(h) -> str:
    if not isinstance(h, dict) or not h.get("status"):
        return ""
    t = f"{h['status']} ({h['aangeleverd_id']})" if h.get("aangeleverd_id") else h["status"]
    if h.get("motivatie"):
        t += f" — {h['motivatie']}"
    return t


def uitvoer_text(uitvoer, namen: dict) -> str:
    if not isinstance(uitvoer, dict) or not uitvoer.get("begrip_id"):
        return ""
    t = begrip_ref(uitvoer["begrip_id"], namen)
    return t + (f" — {uitvoer['toelichting']}" if uitvoer.get("toelichting") else "")


def invoer_text(invoer, namen: dict) -> str:
    delen = []
    for i in (invoer or []):
        if not isinstance(i, dict):
            continue
        delen.append(begrip_ref(i.get("begrip_id"), namen)
                     + (f" — {i['toelichting']}" if i.get("toelichting") else ""))
    return "; ".join(d for d in delen if d)


def parameters_text(params, namen: dict) -> str:
    delen = []
    for p in (params or []):
        if not isinstance(p, dict):
            continue
        stuk = [begrip_ref(p.get("begrip_id"), namen)]
        if p.get("waarde"):
            stuk.append(f"= {p['waarde']}" + (f" {p['eenheid']}" if p.get("eenheid") else ""))
        else:
            stuk.append("(waarde in delegatie)")
        if p.get("geldigheid"):
            stuk.append(f"[{p['geldigheid']}]")
        if p.get("toelichting"):
            stuk.append(f"— {p['toelichting']}")
        delen.append(" ".join(s for s in stuk if s))
    return "; ".join(delen)


def voorwaarden_text(vws, namen: dict) -> str:
    delen = []
    for i, v in enumerate(vws or []):
        if not isinstance(v, dict):
            continue
        prefix = f"{v['verbinding']} " if i > 0 and v.get("verbinding") else ""
        ids = ", ".join(begrip_ref(x, namen) for x in (v.get("begrip_ids") or []))
        delen.append(prefix + (v.get("tekst") or "") + (f" [{ids}]" if ids else ""))
    return " · ".join(delen)


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


def sectie_3(a3: dict) -> list[str]:
    bron_label = {b.get("bron_id"): (b.get("label") or bron_titel(b)) for b in (a3.get("bronnen") or [])}
    namen = begrip_naam_map(a3.get("begrippen"))
    regels = [
        "## 3. Activiteit 3 — Betekenis (gedeeld over het werkgebied)",
        "",
        "### 3a — Begrippen",
        "",
        "| Begripsnaam | Synoniemen | Klasse | Definitie | Grondformulering | Voorbeeld | "
        "Kenmerken / relaties | Verwijst naar | Herkomst | Vindplaats | Twijfel/aanname |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for b in sorted(a3.get("begrippen", []),
                    key=lambda b: jas_sorteersleutel(b.get("klasse", ""))):
        kenmerken = "; ".join(x for x in [b.get("kenmerken") or "",
                                          relaties_text(b.get("relaties"), namen)] if x)
        verwijst = ", ".join(begrip_ref(x, namen)
                             for x in (b.get("verwijst_naar_begrippen") or []))
        regels.append(
            f"| {cel(b.get('naam'))} | {cel(', '.join(b.get('synoniemen') or []))} | "
            f"{cel(b.get('klasse'))} | {cel(definitie_text(b))} | {cel(b.get('grondformulering'))} | "
            f"{cel(b.get('voorbeeld'))} | {cel(kenmerken)} | {cel(verwijst)} | "
            f"{cel(herkomst_text(b.get('herkomst')))} | "
            f"{cel(vindplaats_text(b.get('vindplaatsen'), bron_label))} | {cel(b.get('twijfel'))} |"
        )
    regels += ["", "### 3b — Afleidingsregels", ""]
    for r in a3.get("afleidingsregels", []):
        regels += [
            f"#### {r.get('naam', TODO)} — {r.get('type', TODO)}",
            "",
            f"- **Uitvoer:** {uitvoer_text(r.get('uitvoer'), namen) or TODO}",
            f"- **Invoer:** {invoer_text(r.get('invoer'), namen) or TODO}",
            f"- **Parameters:** {parameters_text(r.get('parameters'), namen) or TODO}",
            f"- **Voorwaarden:** {voorwaarden_text(r.get('voorwaarden'), namen) or TODO}",
        ]
        if r.get("toelichting"):
            regels.append(f"- **Toelichting:** {r['toelichting']}")
        if r.get("markering_ids"):
            regels.append(f"- **Markeringen:** {', '.join(r['markering_ids'])}")
        regels += [
            f"- **Vindplaats / bron:** {vindplaats_text(r.get('vindplaatsen'), bron_label) or TODO}",
            f"- **Twijfel/aanname:** {r.get('twijfel', TODO)}",
            "",
        ]
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


def sectie_4(a3: dict, rondes2, rondes3) -> list[str]:
    regels = ["## 4. Reviewlog en aandachtspunten voor validatie", "", "### Reviewlog", ""]
    regels += reviewlog_regel("Activiteit 2", rondes2)
    regels += reviewlog_regel("Activiteit 3", rondes3)
    regels += [
        "",
        "### Aandachtspunten voor multidisciplinaire validatie",
        "",
        f"> {TODO} — De skill vult dit gestructureerd in (interpretatiekeuzes / open normen /",
        "> openstaande delegaties / aannames / buiten scope), op basis van de twijfelvelden",
        "> hieronder en de validatiepunten uit activiteit 3. Verwijder dit blok na invullen.",
        "",
        "**Ruw materiaal — validatiepunten (activiteit 3):**",
        "",
    ]
    vp = a3.get("validatiepunten", TODO) or TODO
    if isinstance(vp, list):
        regels += [f"- {item}" for item in vp]
    else:
        regels.append(vp)
    regels += [
        "",
    ]
    return regels


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--werk", required=True, type=Path,
                    help="werkmap met activiteit-2/ en activiteit-3/")
    ap.add_argument("--out", required=True, type=Path, help="pad naar het rapport (.md)")
    args = ap.parse_args()

    dir2 = args.werk / "activiteit-2"
    dir3 = args.werk / "activiteit-3"

    ronde2 = laatste_ronde(dir2)
    ronde3 = laatste_ronde(dir3)
    if ronde2 is None:
        sys.exit(f"FOUT: geen ronde gevonden in {dir2}")
    if ronde3 is None:
        sys.exit(f"FOUT: geen ronde gevonden in {dir3}")

    a2 = laad_json(ronde2 / "analyse.json")
    a3 = laad_json(ronde3 / "analyse.json")
    rondes2 = verzamel_rondes(dir2)
    rondes3 = verzamel_rondes(dir3)

    regels: list[str] = [
        titel(a2),
        "",
        "> Analyse volgens de methode Wetsanalyse (Ausems, Bulles & Lokin), activiteit 2 + 3.",
        "> Dit is een **concept-analyse als hulpmiddel**: bedoeld voor multidisciplinaire validatie",
        "> (jurist, informatieanalist, ICT). Interpretatiekeuzes zijn als zodanig gemarkeerd.",
        "",
    ]
    regels += sectie_0(a2)
    regels += sectie_bronnen(a2)
    regels += sectie_3(a3)
    regels += sectie_4(a3, rondes2, rondes3)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(regels) + "\n", encoding="utf-8")

    aantal_todo = ("\n".join(regels)).count(TODO)
    print(f"Rapport geschreven naar {args.out}")
    print(f"Bron: activiteit-2 {ronde2.name}, activiteit-3 {ronde3.name}")
    if aantal_todo:
        print(f"Let op: {aantal_todo}× {TODO} — vul deze handmatig/in de skill aan "
              "(sectie 0-metadata en de §4-aandachtspunten).")


if __name__ == "__main__":
    main()
