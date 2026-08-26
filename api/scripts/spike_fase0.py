#!/usr/bin/env python3
"""Fase 0-spike — de-risk de kern tegen de échte MCP + Azure-adapter.

Haalt één artikel op via de MCP, genereert een activiteit-2 analyse via de LLM-adapter, en
draait de validatie (zacht + hard brongetrouwheid). Bewijst het moeilijkste stuk vóór de infra.

Vereist env (zie api/.env.example): WETTENBANK_TOKEN, LLM_MODEL, LLM_API_BASE, LLM_API_KEY.
Vereist de 'llm'-extra:  uv run --extra llm python scripts/spike_fase0.py BWBR0004770 9 1
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.engine import steps  # noqa: E402
from app.llm.litellm_client import build_llm_client  # noqa: E402
from app.profiles import _config_uit_env  # noqa: E402
from app.validation import brongetrouwheid_check, schema_check  # noqa: E402
from app.wettenbank import WettenbankClient, map_artikel_naar_analyse_basis  # noqa: E402


async def main() -> int:
    bwb_id = sys.argv[1] if len(sys.argv) > 1 else "BWBR0004770"
    artikel = sys.argv[2] if len(sys.argv) > 2 else "9"
    lid = sys.argv[3] if len(sys.argv) > 3 else None

    settings = get_settings()
    wb = WettenbankClient(settings)
    # Spike draait standalone (geen DB-profielen): bouw de client uit de env-config.
    llm = build_llm_client(_config_uit_env(settings))

    print(f"→ Ophalen {bwb_id} art. {artikel}" + (f" lid {lid}" if lid else "") + " via MCP …")
    artikel_data = await wb.artikel(bwb_id, artikel, lid)
    basis = map_artikel_naar_analyse_basis(artikel_data)
    print(f"  bronreferentie: {basis['bronreferentie']}  ({len(basis['leden'])} lid/leden)")

    print("→ Activiteit 2 genereren via de LLM-adapter …")
    # Eén bron; de cross-referentie-fetch (inventaris/opgehaald) slaan we hier bewust over —
    # die raakt de LLM-call niet en houdt de spike deterministisch.
    analyse, prov = await steps.genereer_act2_bron(
        llm, basis, ronde=1, analysefocus=None, inventaris=None, opgehaald=None
    )

    # De validatie werkt werkgebied-breed; wikkel de ene bron in de werkgebied-vorm.
    werkgebied = {"werkgebied": {"naam": "spike"}, "bronnen": [analyse]}
    fouten, waarschuwingen = schema_check(werkgebied, "2")
    schendingen = brongetrouwheid_check(werkgebied, "2")

    print(f"\n  model={prov['model']}  markeringen={len(analyse.get('markeringen', []))}")
    print(f"  schema-fouten: {len(fouten)}  waarschuwingen: {len(waarschuwingen)}")
    print(f"  brongetrouwheid-schendingen: {len(schendingen)}")
    for s in schendingen:
        print(f"    ✗ {s}")

    out = Path("spike_act2.json")
    out.write_text(json.dumps(analyse, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  geschreven: {out}")

    ok = not schendingen and not fouten
    print("\n" + ("✓ SPIKE GESLAAGD" if ok else "✗ SPIKE: er zijn blokkerende bevindingen"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
