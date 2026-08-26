#!/usr/bin/env python3
"""Rapport-/modelviewer voor de regelspraak-skill.

Serveert de viewer.html met het gegenereerde model.json en biedt twee acties: het
opslaan van bewerkingen op de vrije-tekstvelden (reviewlogs + validatiepunten), en het
wegschrijven van de RegelSpraak-tekst als .rs- én Markdown-bestand.

Geen dependencies buiten de standaardbibliotheek.

Gebruik:
    python rapport_server.py --input <model.json> [--port 3121] [--no-browser]
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

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "viewer.html"

# Canonieke volgorde van de GegevensSpraak-declaraties in de tekstexport.
GS_VOLGORDE = [
    "eenheidssystemen", "domeinen", "dimensies", "tijdlijnen", "dagsoorten",
    "objecttypen", "feittypen", "parameters",
]


# --- tekstexport (.rs / .md) --------------------------------------------------

def render_rs(model: dict) -> str:
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
                regels += [tekst, ""]
    regels += ["```", "", "## 2. RegelSpraak-regels", "", "```regelspraak"]
    for r in (model.get("regels") or []):
        tekst = (r.get("regelspraak_tekst") or "").strip()
        if tekst:
            regels += [tekst, ""]
    regels += ["```", "", "## 3. Reviewlog en aandachtspunten", ""]
    regels.append(f"- **GegevensSpraak:** {model.get('reviewlog_gegevensspraak') or '_TODO_'}")
    regels.append(f"- **Regels:** {model.get('reviewlog_regels') or '_TODO_'}")
    regels += ["", "### Aandachtspunten voor validatie", ""]
    vp = model.get("validatiepunten") or []
    if isinstance(vp, str):
        vp = [vp] if vp.strip() else []
    regels += [f"- {v}" for v in vp] if vp else ["_TODO_"]
    regels.append("")
    return "\n".join(regels) + "\n"


def slug(model: dict) -> str:
    naam = (model.get("werkgebied") or {}).get("naam") or ""
    s = re.sub(r"[^a-z0-9]+", "-", naam.lower()).strip("-")
    return s or "regelspraak"


# --- HTTP server -------------------------------------------------------------

def build_html(model_data: dict) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    data_json = json.dumps(model_data, ensure_ascii=False).replace("</script>", "<\\/script>")
    return template.replace("/*__EMBEDDED_DATA__*/", f"const EMBEDDED_DATA = {data_json};")


class RapportHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, html: str = "", model_pad: Path = None, **kwargs):
        self._html = html
        self._model_pad = model_pad
        super().__init__(*args, **kwargs)

    def log_message(self, *args):
        pass

    def _send(self, code: int, body: bytes, content_type: str):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _laad_model(self):
        return json.loads(self._model_pad.read_text(encoding="utf-8"))

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, self._html.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(404, b"Not found", "text/plain; charset=utf-8")

    def do_POST(self):
        if self.path == "/schrijf-rs":
            try:
                model = self._laad_model()
            except (json.JSONDecodeError, OSError) as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)}).encode("utf-8"),
                           "application/json; charset=utf-8")
                return
            basis = self._model_pad.parent / slug(model)
            rs_pad = basis.with_suffix(".rs")
            md_pad = basis.with_suffix(".md")
            try:
                rs_pad.write_text(render_rs(model), encoding="utf-8")
                md_pad.write_text(render_md(model), encoding="utf-8")
            except OSError as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)}).encode("utf-8"),
                           "application/json; charset=utf-8")
                return
            self._send(200, json.dumps({"ok": True, "rs": str(rs_pad), "md": str(md_pad)}).encode("utf-8"),
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

        try:
            huidig = self._laad_model()
        except (json.JSONDecodeError, OSError) as e:
            self._send(500, json.dumps({"ok": False, "error": str(e)}).encode("utf-8"),
                       "application/json; charset=utf-8")
            return

        if "reviewlog_gegevensspraak" in body:
            huidig["reviewlog_gegevensspraak"] = str(body["reviewlog_gegevensspraak"])
        if "reviewlog_regels" in body:
            huidig["reviewlog_regels"] = str(body["reviewlog_regels"])
        if "validatiepunten" in body:
            vp = body["validatiepunten"]
            if isinstance(vp, str):
                vp = [r.strip() for r in vp.split("\n") if r.strip()]
            huidig["validatiepunten"] = vp

        tmp_pad = self._model_pad.with_suffix(".json.tmp")
        try:
            tmp_pad.write_text(json.dumps(huidig, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp_pad, self._model_pad)
        except OSError as e:
            self._send(500, json.dumps({"ok": False, "error": str(e)}).encode("utf-8"),
                       "application/json; charset=utf-8")
            return

        self.__class__._refresh_html(huidig)
        self._send(200, b'{"ok":true}', "application/json; charset=utf-8")

    @classmethod
    def _refresh_html(cls, data: dict):
        pass  # overschreven door de factory-closure hieronder


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
    parser = argparse.ArgumentParser(description="Regelspraak rapport-/modelviewer")
    parser.add_argument("--input", type=Path, required=True, help="Pad naar model.json")
    parser.add_argument("--port", type=int, default=3121, help="Serverpoort (default 3121)")
    parser.add_argument("--no-browser", action="store_true", help="Open de browser niet")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"model.json niet gevonden: {args.input}", file=sys.stderr)
        sys.exit(1)
    if not TEMPLATE.exists():
        print(f"Template niet gevonden: {TEMPLATE}", file=sys.stderr)
        sys.exit(1)

    model_data = json.loads(args.input.read_text(encoding="utf-8"))
    html_container = [build_html(model_data)]

    class Handler(RapportHandler):
        @classmethod
        def _refresh_html(cls, data: dict):
            html_container[0] = build_html(data)

    original_init = Handler.__init__

    def patched_init(self, *a, **kw):
        kw["html"] = html_container[0]
        original_init(self, *a, **kw)

    Handler.__init__ = patched_init
    handler = partial(Handler, model_pad=args.input)

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
    wg = model_data.get("werkgebied") or {}
    n_regels = len(model_data.get("regels") or [])
    print(f"\n  Regelspraak - model {wg.get('naam', 'werkgebied')} ({n_regels} regel(s))")
    print(f"  -----------------------------------------")
    print(f"  URL:     {url}")
    print(f"  Model:   {args.input}")
    print(f"\n  Bekijk het model, pas de §-velden aan en klik Opslaan.")
    print(f"  Schrijf de RegelSpraak-tekst (.rs/.md) via de knop in de browser.")
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
