#!/usr/bin/env python3
"""Review-server voor de wetsanalyse-skill (human-in-the-loop checkpoint).

Serveert een lokale reviewpagina met het tussenresultaat van activiteit 2 of 3.
De analist geeft per item én in het algemeen desgewenst feedback en klikt op de
verstuurknop (zonder feedback telt dat als akkoord); de feedback wordt naar een
JSON-bestand geschreven dat de skill daarna inleest en verwerkt.

Geen dependencies buiten de standaardbibliotheek.

Gebruik:
    python review_server.py \
        --input <tussenresultaat.json> \
        --activiteit 2|3 \
        --feedback-out <pad/feedback-activiteit-2.json> \
        [--port 3118]

Het tussenresultaat-JSON volgt het schema in references/review-checkpoints.md.
"""

import argparse
import io
import json
import os
import signal as _signal
import subprocess
import sys
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "review.html"


def load_vorige(vorige_dir: Path) -> dict | None:
    """Laad de vorige ronde (analyse + feedback) als context voor de reviewpagina.

    Verwacht in `vorige_dir`: `analyse.json` en (optioneel) `feedback.json`.
    Ontbrekende of corrupte bestanden worden stil overgeslagen — de vorige-context
    is hulpinformatie, geen harde eis.
    """
    if not vorige_dir or not vorige_dir.is_dir():
        return None
    out: dict = {}
    for key, naam in (("analyse", "analyse.json"), ("feedback", "feedback.json")):
        pad = vorige_dir / naam
        if pad.exists():
            try:
                out[key] = json.loads(pad.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
    return out or None


def build_html(input_data: dict, activiteit: str, ronde: int = 1,
               vorige: dict | None = None) -> str:
    """Embed het tussenresultaat in de HTML-template."""
    template = TEMPLATE.read_text(encoding="utf-8")
    embedded = {"activiteit": activiteit, "analyse": input_data, "ronde": ronde}
    if vorige:
        embedded["vorige"] = vorige
    # Escape </script> zodat een veldwaarde de script-tag niet kan sluiten.
    data_json = json.dumps(embedded, ensure_ascii=False).replace("</script>", "<\\/script>")
    return template.replace(
        "/*__EMBEDDED_DATA__*/",
        f"const EMBEDDED_DATA = {data_json};",
    )


class ReviewHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, html: str = "", feedback_out: Path = None, **kwargs):
        self._html = html
        self._feedback_out = feedback_out
        super().__init__(*args, **kwargs)

    def log_message(self, *args):  # stil houden
        pass

    def _send(self, code: int, body: bytes, content_type: str):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, self._html.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(404, b"Not found", "text/plain; charset=utf-8")

    def do_POST(self):
        if self.path != "/feedback":
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        try:
            length = max(0, int(self.headers.get("Content-Length", 0)))
        except (TypeError, ValueError):
            length = 0
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._send(400, b'{"ok":false,"error":"invalid json"}',
                       "application/json; charset=utf-8")
            return
        self._feedback_out.parent.mkdir(parents=True, exist_ok=True)
        # Atomisch schrijven via tijdelijk bestand (zelfde patroon als rapport_server.py): een
        # crash mid-write laat geen getrunceerde feedback.json achter.
        tmp_pad = self._feedback_out.with_suffix(".json.tmp")
        try:
            tmp_pad.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(tmp_pad, self._feedback_out)
        except OSError as e:
            self._send(500, json.dumps({"ok": False, "error": str(e)}).encode("utf-8"),
                       "application/json; charset=utf-8")
            return
        self._send(200, b'{"ok":true}', "application/json; charset=utf-8")


def _kill_port(port: int) -> None:
    """Beëindig een eventueel proces dat al op de poort luistert (Windows + Unix)."""
    import sys as _sys
    try:
        if _sys.platform == "win32":
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
    parser = argparse.ArgumentParser(description="Wetsanalyse review-server")
    parser.add_argument("--input", type=Path, required=True,
                        help="Pad naar tussenresultaat-JSON (activiteit 2 of 3)")
    parser.add_argument("--activiteit", choices=["2", "3"], required=True,
                        help="Welke activiteit wordt gereviewd")
    parser.add_argument("--feedback-out", type=Path, required=True,
                        help="Pad waar de feedback-JSON wordt weggeschreven")
    parser.add_argument("--ronde", type=int, default=1,
                        help="Welke reviewronde dit is (default 1)")
    parser.add_argument("--vorige", type=Path, default=None,
                        help="Map van de vorige ronde (met analyse.json + feedback.json) "
                             "om als context te tonen; weglaten bij ronde 1")
    parser.add_argument("--port", type=int, default=3118, help="Serverpoort (default 3118)")
    parser.add_argument("--no-browser", action="store_true",
                        help="Open de browser niet automatisch")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Invoerbestand niet gevonden: {args.input}", file=sys.stderr)
        sys.exit(1)
    if not TEMPLATE.exists():
        print(f"Template niet gevonden: {TEMPLATE}", file=sys.stderr)
        sys.exit(1)

    input_data = json.loads(args.input.read_text(encoding="utf-8"))
    vorige = load_vorige(args.vorige) if args.vorige else None
    html = build_html(input_data, args.activiteit, args.ronde, vorige)

    _kill_port(args.port)
    handler = partial(ReviewHandler, html=html, feedback_out=args.feedback_out)
    try:
        server = HTTPServer(("127.0.0.1", args.port), handler)
        port = args.port
    except OSError:
        server = HTTPServer(("127.0.0.1", 0), handler)
        port = server.server_address[1]

    # Zorg voor UTF-8 stdout op Windows (cp1252-terminals crashen op em-dash e.d.)
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    url = f"http://localhost:{port}"
    print(f"\n  Wetsanalyse - review activiteit {args.activiteit} (ronde {args.ronde})")
    print(f"  -----------------------------------------")
    print(f"  URL:       {url}")
    print(f"  Invoer:    {args.input}")
    print(f"  Feedback:  {args.feedback_out}")
    if vorige:
        print(f"  Vorige:    {args.vorige}")
    print(f"\n  Open de URL, geef desgewenst feedback en klik op de verstuurknop (leeg = akkoord).")
    print(f"  Druk daarna Ctrl+C of laat de skill verdergaan.\n")
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
