"""Markdown-export uit het werkgebied-rapport.json (de primaire bron). Bewust compact; de
HTML-viewer blijft de rijke presentatie. Spiegelt de sectie-indeling van rapport_server.py."""

from __future__ import annotations

import re

from .validation import jas_sorteersleutel


def _lid_suffix(label: str, lid) -> str:
    """Lid-suffix voor een vindplaats. Normaliseert de lid-waarde (strip een eventuele
    `lid `-prefix, zodat zowel "1" als "lid 1" op "1" uitkomt) en laat de suffix weg als het
    bron-label het lid al bevat (bron op lid-niveau) of als er geen lid is (lid-loos artikel)."""
    s = re.sub(r"^\s*lid\s+", "", str(lid or "").strip(), flags=re.IGNORECASE)
    if not s or label.rstrip().lower().endswith(f"lid {s}".lower()):
        return ""
    return f" lid {s}"


def _tabel(headers: list[str], rijen: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rijen:
        out.append("| " + " | ".join((c or "").replace("\n", " ").replace("|", "\\|") for c in r) + " |")
    return out


def _bron_titel(b: dict) -> str:
    if b.get("label"):
        return b["label"]
    if b.get("wet"):
        lid = f" lid {b['lid']}" if b.get("lid") else ""
        return f"{b['wet']} art. {b.get('artikel', '')}{lid}"
    return b.get("bron_id", "bron")


def _vindplaats(vps, bron_label: dict) -> str:
    if not isinstance(vps, list) or not vps:
        return ""
    delen = []
    for vp in vps:
        lbl = bron_label.get(vp.get("bron_id"), vp.get("bron_id", ""))
        delen.append(lbl + _lid_suffix(lbl, vp.get("lid")))
    return "; ".join(d for d in delen if d)


def rapport_naar_markdown(r: dict) -> str:
    wg = r.get("werkgebied") or {}
    bronnen = r.get("bronnen") or []
    bron_label = {b.get("bron_id"): (b.get("label") or _bron_titel(b)) for b in bronnen}

    titel = wg.get("naam") or (_bron_titel(bronnen[0]) if len(bronnen) == 1 else "werkgebied")
    L: list[str] = [f"# Wetsanalyse — {titel}", ""]

    L.append("## 0. Werkgebied en afbakening")
    for label, key in [("Werkgebied", "naam"), ("Hoofdvraag", "hoofdvraag"),
                       ("Omschrijving", "omschrijving"), ("Afbakening", "scoping")]:
        if (wg.get(key) or "").strip():
            L.append(f"- **{label}:** {wg[key]}")
    L.append("")
    L.append(f"### Bronnen in het werkgebied ({len(bronnen)})")
    for b in bronnen:
        det = " · ".join(x for x in [b.get("bwbId"), b.get("versiedatum"), b.get("bronreferentie")] if x)
        L.append(f"- **{_bron_titel(b)}** — {det}")
    L.append("")

    # §1/§2 per bron
    L.append("## 1/2. Bronnen — wettekst, markeringen en verwijzingen")
    for i, b in enumerate(bronnen, 1):
        L += ["", f"### Bron {i} — {_bron_titel(b)}", ""]
        L.append("**Wettekst**")
        for lid in b.get("leden", []):
            L.append(f"- **Lid {lid.get('lid', '')}:** {lid.get('tekst', '')}")
        L += ["", "**Markeringen en classificatie**"]
        markeringen = sorted(b.get("markeringen", []),
                             key=lambda m: jas_sorteersleutel(m.get("klasse", "")))
        L += _tabel(
            ["Id", "Formulering", "JAS-klasse", "Vindplaats", "Toelichting"],
            [[m.get("id", ""), m.get("formulering", ""), m.get("klasse", ""),
              m.get("vindplaats", ""), m.get("toelichting", "")] for m in markeringen],
        )
        verwijzingen = b.get("verwijzingen", [])
        if verwijzingen:
            L += ["", "**Verwijzingen**"]
            rijen = []
            for v in verwijzingen:
                doel = v.get("doel") or {}
                doel_tekst = doel.get("label", "") or doel.get("target", "")
                if doel.get("target"):
                    doel_tekst = f"[{doel_tekst}](https://wetten.overheid.nl/{doel['target']})"
                rijen.append([v.get("id", ""), v.get("functie", ""), doel_tekst,
                              v.get("bron_lid", ""), v.get("status", ""), v.get("betekenis", "")])
            L += _tabel(["Id", "Functie", "Doel", "Bron", "Status", "Betekenis"], rijen)
        if (b.get("samenhang") or "").strip():
            L += ["", f"**Samenhang:** {b['samenhang']}"]
    L.append("")

    L.append("## 3. Begrippen en afleidingsregels (gedeeld over het werkgebied)")
    L.append("### Begrippen")
    begrippen = sorted(r.get("begrippen", []),
                       key=lambda b: jas_sorteersleutel(b.get("klasse", "")))
    L += _tabel(
        ["Id", "Naam", "Synoniemen", "Klasse", "Definitie", "Vindplaats"],
        [[b.get("id", ""), b.get("naam", ""), ", ".join(b.get("synoniemen") or []),
          b.get("klasse", ""), b.get("definitie", ""), _vindplaats(b.get("vindplaatsen"), bron_label)]
         for b in begrippen],
    )
    L += ["", "### Afleidingsregels"]
    L += _tabel(
        ["Id", "Naam", "Type", "Formulering", "Vindplaats"],
        [[a.get("id", ""), a.get("naam", ""), a.get("type", ""), a.get("formulering", ""),
          _vindplaats(a.get("vindplaatsen"), bron_label)] for a in r.get("afleidingsregels", [])],
    )
    L.append("")

    L.append("## 4. Reviewlog en aandachtspunten")
    rl = r.get("reviewlog", {})
    for act in ("activiteit2", "activiteit3"):
        sv = (rl.get(act, {}) or {}).get("samenvatting", "")
        if sv:
            L.append(f"- **Reviewlog {act}:** {sv}")
    if (r.get("aandachtspunten") or "").strip():
        L += ["", "### Aandachtspunten voor multidisciplinaire validatie", r["aandachtspunten"]]
    L.append("")
    return "\n".join(L)
