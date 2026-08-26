#!/usr/bin/env python3
"""Rapport-server voor de wetsanalyse-skill.

Serveert de rapport.html-viewer met het gegenereerde rapport.json en biedt twee
acties: het opslaan van bewerkingen op de vrije-tekstvelden (§4), en het
downloaden van het rapport als Markdown-bestand.

Geen dependencies buiten de standaardbibliotheek.

Gebruik:
    python rapport_server.py \\
        --input <rapport.json> \\
        [--port 3119] \\
        [--no-browser]
"""

import argparse
import io
import json
import os
import re
import signal as _signal
import subprocess
import sys
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_analyse import jas_sorteersleutel  # noqa: E402 — sibling-script, zelfde map

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "rapport.html"


# --- Markdown-generatie uit rapport.json -------------------------------------

def cel(tekst) -> str:
    if not tekst:
        return ""
    return str(tekst).replace("|", "\\|").replace("\n", "<br>").strip()


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


def rapport_naar_md(d: dict) -> str:
    regels: list[str] = []
    wg = d.get("werkgebied") or {}
    bronnen = d.get("bronnen") or []
    bron_label = {b.get("bron_id"): (b.get("label") or bron_titel(b)) for b in bronnen}

    titel = wg.get("naam") or (bron_titel(bronnen[0]) if len(bronnen) == 1 else "werkgebied")
    regels += [
        f"# Wetsanalyse — {titel}",
        "",
        "> Analyse volgens de methode Wetsanalyse (Ausems, Bulles & Lokin), activiteit 2 + 3.",
        "> Dit is een **concept-analyse als hulpmiddel**: bedoeld voor multidisciplinaire validatie",
        "> (jurist, informatieanalist, ICT). Interpretatiekeuzes zijn als zodanig gemarkeerd.",
        "",
    ]

    # §0 Werkgebied en afbakening
    regels += [
        "## 0. Werkgebied en afbakening",
        "",
        f"- **Werkgebied:** {wg.get('naam', '')}",
        f"- **Hoofdvraag / analysefocus:** {wg.get('hoofdvraag') or wg.get('analysefocus', '')}",
        f"- **Omschrijving:** {wg.get('omschrijving', '')}",
        f"- **Afbakening (scoping):** {wg.get('scoping', '')}",
        "",
        f"### Bronnen in het werkgebied ({len(bronnen)})",
        "",
    ]
    for b in bronnen:
        det = " · ".join(filter(None, [b.get("bwbId"), b.get("versiedatum"), b.get("bronreferentie")]))
        regels.append(f"- **{bron_titel(b)}** — {det}")
    regels.append("")

    # §1/§2 Per bron: wettekst, markeringen, verwijzingen, samenhang
    regels += ["## 1/2. Bronnen — wettekst, markeringen en verwijzingen", ""]
    for i, b in enumerate(bronnen, 1):
        regels += [f"### Bron {i} — {bron_titel(b)}", ""]
        regels += ["**Wettekst (letterlijk)**", ""]
        for lid in b.get("leden", []):
            regels.append(f"**Lid {lid.get('lid', '?')}.** {lid.get('tekst', '')}")
            regels.append("")
        regels += [
            "**Markeringen & classificaties**",
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
        regels.append("")
        verwijzingen = b.get("verwijzingen", [])
        if verwijzingen:
            regels += [
                "**Verwijzingen**",
                "",
                "| # | Functie | Doel | Bron | Soort | Status | Betekenis |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
            for v in verwijzingen:
                doel = v.get("doel") or {}
                doel_tekst = doel.get("label") or doel.get("target") or ""
                if doel.get("target"):
                    doel_tekst = f"[{doel_tekst}](https://wetten.overheid.nl/{doel['target']})"
                regels.append(
                    f"| {cel(v.get('id'))} | {cel(v.get('functie'))} | {cel(doel_tekst)} | "
                    f"{cel(v.get('bron_lid'))} | {cel(v.get('soort'))} | {cel(v.get('status'))} | "
                    f"{cel(v.get('betekenis'))} |"
                )
            regels.append("")
        if b.get("samenhang"):
            regels += ["**Samenhang centrale klassen**", "", b["samenhang"], ""]

    # §3 Begrippen + afleidingsregels (gedeeld over het werkgebied)
    namen = begrip_naam_map(d.get("begrippen"))
    regels += [
        "## 3. Activiteit 3 — Betekenis (gedeeld over het werkgebied)",
        "",
        "### 3a — Begrippen",
        "",
        "| Begripsnaam | Synoniemen | Klasse | Definitie | Grondformulering | Voorbeeld | "
        "Kenmerken / relaties | Verwijst naar | Herkomst | Vindplaats | Twijfel/aanname |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for b in sorted(d.get("begrippen", []),
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
    for r in d.get("afleidingsregels", []):
        regels += [f"#### {r.get('naam', '')} — {r.get('type', '')}", ""]
        for lbl, waarde in [
            ("Uitvoer", uitvoer_text(r.get("uitvoer"), namen)),
            ("Invoer", invoer_text(r.get("invoer"), namen)),
            ("Parameters", parameters_text(r.get("parameters"), namen)),
            ("Voorwaarden", voorwaarden_text(r.get("voorwaarden"), namen)),
            ("Toelichting", r.get("toelichting") or ""),
            ("Markeringen", ", ".join(r.get("markering_ids") or [])),
        ]:
            if waarde:
                regels.append(f"- **{lbl}:** {waarde}")
        vp = vindplaats_text(r.get("vindplaatsen"), bron_label)
        if vp:
            regels.append(f"- **Vindplaats / bron:** {vp}")
        if r.get("twijfel"):
            regels.append(f"- **Twijfel/aanname:** {r['twijfel']}")
        regels.append("")

    # §4 Reviewlog + aandachtspunten
    rl = d.get("reviewlog", {})
    act2_samen = (rl.get("activiteit2") or {}).get("samenvatting", "")
    act3_samen = (rl.get("activiteit3") or {}).get("samenvatting", "")
    aandacht = d.get("aandachtspunten", "")

    regels += [
        "## 4. Reviewlog en aandachtspunten voor validatie",
        "",
        "### Reviewlog",
        "",
        f"- **Activiteit 2:** {act2_samen or '_TODO_'}",
        f"- **Activiteit 3:** {act3_samen or '_TODO_'}",
        "",
        "### Aandachtspunten voor multidisciplinaire validatie",
        "",
        aandacht or "_TODO_",
        "",
    ]

    return "\n".join(regels) + "\n"


def md_bestandsnaam(d: dict) -> str:
    wg = d.get("werkgebied") or {}
    bronnen = d.get("bronnen") or []
    slug = re.sub(r"[^a-z0-9]+", "-", (wg.get("naam") or "").lower()).strip("-")
    if not slug and bronnen:
        b = bronnen[0]
        bwb = re.sub(r"[^a-z0-9]", "", (b.get("bwbId") or "").lower())
        # Punt in het artikelnummer behouden (bv. "9.5").
        art = re.sub(r"[^a-z0-9.]", "", str(b.get("artikel") or "").lower())
        lid = f"-lid{b['lid']}" if b.get("lid") else ""
        slug = f"{bwb}-art{art}{lid}" if bwb and art else ""
    slug = slug or "analyserapport"
    return f"analyserapport-{slug}.md"


# --- HTTP server -------------------------------------------------------------

def build_html(rapport_data: dict) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    # Escape </script> zodat een veldwaarde de script-tag niet kan sluiten.
    data_json = json.dumps(rapport_data, ensure_ascii=False).replace("</script>", "<\\/script>")
    return template.replace("/*__EMBEDDED_DATA__*/", f"const EMBEDDED_DATA = {data_json};")


class RapportHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, html: str = "", rapport_pad: Path = None, **kwargs):
        self._html = html
        self._rapport_pad = rapport_pad
        super().__init__(*args, **kwargs)

    def log_message(self, *args):
        pass

    def _send(self, code: int, body: bytes, content_type: str, extra_headers: dict = None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, self._html.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(404, b"Not found", "text/plain; charset=utf-8")

    def do_POST(self):
        if self.path == "/schrijf-md":
            try:
                data = json.loads(self._rapport_pad.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)}).encode("utf-8"),
                           "application/json; charset=utf-8")
                return
            md = rapport_naar_md(data)
            naam = md_bestandsnaam(data)
            md_pad = self._rapport_pad.parent / naam
            try:
                md_pad.write_text(md, encoding="utf-8")
            except OSError as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)}).encode("utf-8"),
                           "application/json; charset=utf-8")
                return
            self._send(200, json.dumps({"ok": True, "pad": str(md_pad)}).encode("utf-8"),
                       "application/json; charset=utf-8")
            return

        if self.path != "/opslaan":
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return

        try:
            length = max(0, int(self.headers.get("Content-Length", 0)))
        except (TypeError, ValueError):
            length = 0
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._send(400, b'{"ok":false,"error":"invalid json"}',
                       "application/json; charset=utf-8")
            return

        # Lees huidig rapport.json, pas alleen de drie bewerkbare velden aan.
        try:
            huidig = json.loads(self._rapport_pad.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            self._send(500, json.dumps({"ok": False, "error": str(e)}).encode("utf-8"),
                       "application/json; charset=utf-8")
            return

        if "reviewlog_act2" in body:
            huidig.setdefault("reviewlog", {}).setdefault("activiteit2", {})
            huidig["reviewlog"]["activiteit2"]["samenvatting"] = str(body["reviewlog_act2"])
        if "reviewlog_act3" in body:
            huidig.setdefault("reviewlog", {}).setdefault("activiteit3", {})
            huidig["reviewlog"]["activiteit3"]["samenvatting"] = str(body["reviewlog_act3"])
        if "aandachtspunten" in body:
            huidig["aandachtspunten"] = str(body["aandachtspunten"])

        # Atomisch schrijven via tijdelijk bestand.
        tmp_pad = self._rapport_pad.with_suffix(".json.tmp")
        try:
            tmp_pad.write_text(json.dumps(huidig, ensure_ascii=False, indent=2),
                               encoding="utf-8")
            os.replace(tmp_pad, self._rapport_pad)
        except OSError as e:
            self._send(500, json.dumps({"ok": False, "error": str(e)}).encode("utf-8"),
                       "application/json; charset=utf-8")
            return

        # Ververs de in-memory HTML met de nieuwe data.
        self.__class__._refresh_html(huidig)

        self._send(200, b'{"ok":true}', "application/json; charset=utf-8")

    @classmethod
    def _refresh_html(cls, data: dict):
        pass  # wordt overschreven door de factory-closure hieronder


def _kill_port(port: int) -> None:
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["powershell", "-Command",
                 f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue"
                 " | Select-Object -ExpandProperty OwningProcess"],
                capture_output=True, text=True, timeout=10,
            )
            for pid in set(result.stdout.split()):
                if pid.strip() and pid.strip() != "0":
                    try:
                        os.kill(int(pid.strip()), _signal.SIGTERM)
                    except (ProcessLookupError, PermissionError, ValueError):
                        pass
        else:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True, text=True, timeout=5,
            )
            for pid in result.stdout.split():
                try:
                    os.kill(int(pid), _signal.SIGTERM)
                except (ProcessLookupError, PermissionError, ValueError):
                    pass
    except (FileNotFoundError, subprocess.SubprocessError):
        pass


def main():
    parser = argparse.ArgumentParser(description="Wetsanalyse rapport-server")
    parser.add_argument("--input", type=Path, required=True,
                        help="Pad naar rapport.json")
    parser.add_argument("--port", type=int, default=3119,
                        help="Serverpoort (default 3119)")
    parser.add_argument("--no-browser", action="store_true",
                        help="Open de browser niet automatisch")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"rapport.json niet gevonden: {args.input}", file=sys.stderr)
        sys.exit(1)
    if not TEMPLATE.exists():
        print(f"Template niet gevonden: {TEMPLATE}", file=sys.stderr)
        sys.exit(1)

    rapport_data = json.loads(args.input.read_text(encoding="utf-8"))

    # Mutable container zodat de handler de HTML kan verversen na /opslaan.
    html_container = [build_html(rapport_data)]

    class Handler(RapportHandler):
        @classmethod
        def _refresh_html(cls, data: dict):
            html_container[0] = build_html(data)

    # Overschrijf html per request zodat verversing na /opslaan zichtbaar is.
    original_init = Handler.__init__

    def patched_init(self, *a, **kw):
        kw["html"] = html_container[0]
        original_init(self, *a, **kw)

    Handler.__init__ = patched_init

    handler = partial(Handler, rapport_pad=args.input)

    _kill_port(args.port)
    try:
        server = HTTPServer(("127.0.0.1", args.port), handler)
        port = args.port
    except OSError:
        server = HTTPServer(("127.0.0.1", 0), handler)
        port = server.server_address[1]

    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    url = f"http://localhost:{port}"
    wg = rapport_data.get("werkgebied") or {}
    bronnen = rapport_data.get("bronnen") or []
    titel = wg.get("naam") or (bron_titel(bronnen[0]) if len(bronnen) == 1 else "werkgebied")
    print(f"\n  Wetsanalyse - rapport {titel} ({len(bronnen)} bron(nen))")
    print(f"  -----------------------------------------")
    print(f"  URL:      {url}")
    print(f"  Rapport:  {args.input}")
    print(f"\n  Bekijk het rapport, pas §4-velden aan en klik Opslaan.")
    print(f"  Download de Markdown via de knop in de browser.")
    print(f"  Druk Ctrl+C om de server te stoppen.\n")

    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server gestopt.")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
