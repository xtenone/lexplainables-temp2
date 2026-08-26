#!/usr/bin/env python3
"""Lees een wetsanalyse-rapport.json deterministisch in als regelspraak-startbasis.

Dit is de brug tussen de skills `wetsanalyse` en `regelspraak`. In plaats van het
rapport handmatig (via prompting) over te nemen, extraheert dit script de delen die
de formalisering voeden naar één `ingest.json`:

- het **werkgebied** (naam + afbakening);
- de **bronnen** als lichte index: identificatie (`bron_id`, `label`, `bwbId`,
  `artikel`, `lid`, `bronreferentie`, `versiedatum`, `pad`), de letterlijke `leden`
  (brongetrouwe context voor de expressies), de uitgaande `verwijzingen` (voor
  domeinen + herkomst), de `Brondefinitie`-markeringen én de markeringen waar een
  begrip/regel via `markering_ids` naar verwijst (`gekoppelde_markeringen`);
- de **begrippen** (activiteit 3a) → voeden GegevensSpraak;
- de **afleidingsregels** (activiteit 3b) → voeden de RegelSpraak-regels.

De oorspronkelijke id's (`b*`, `r*`, `v*`, `m*`, `br*`) blijven behouden, zodat de
`herkomst`-velden van GegevensSpraak/RegelSpraak er één-op-één naar terugverwijzen.
Het script voegt geen interpretatie toe — de eigenlijke vertaling naar RegelSpraak
blijft stap 2/3 van de skill.

Geen dependencies buiten de standaardbibliotheek.

Gebruik:
    python ingest_rapport.py \\
        --rapport analyses/<werkgebied>/rapport.json \\
        --out     analyses/<werkgebied>/regelspraak/werk/ingest.json
"""

import argparse
import json
import sys
from pathlib import Path


# --- helpers ------------------------------------------------------------------

def laad_json(pad: Path) -> dict:
    try:
        return json.loads(pad.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        sys.exit(f"FOUT: kan {pad} niet lezen: {e}")


# Identificerende bron-velden die we letterlijk overnemen (geen interpretatie).
_BRON_ID_VELDEN = (
    "bron_id", "label", "bwbId", "artikel", "lid",
    "versiedatum", "bronreferentie", "pad",
)


def gerefereerde_markering_ids(rapport: dict) -> set:
    """Alle markering-id's waar een begrip of afleidingsregel via `markering_ids` op steunt —
    die act-2-markeringen zijn herkomst-context en gaan gericht mee in de lichte bron."""
    ids: set = set()
    for groep in ("begrippen", "afleidingsregels"):
        for item in (rapport.get(groep) or []):
            ids.update(m for m in (item.get("markering_ids") or []) if m)
    return ids


def lichte_bron(bron: dict, gerefereerd: set) -> dict:
    """Trim een rapport-bron tot wat de formalisering nodig heeft."""
    uit = {veld: bron.get(veld) for veld in _BRON_ID_VELDEN if bron.get(veld) is not None}
    if bron.get("leden"):
        uit["leden"] = bron["leden"]
    if bron.get("verwijzingen"):
        uit["verwijzingen"] = bron["verwijzingen"]
    # De Brondefinitie-markeringen (domeinen/definities) plus de markeringen waar een
    # begrip/regel via `markering_ids` naar verwijst (herkomst-context) gaan mee.
    markeringen = [
        m for m in (bron.get("markeringen") or [])
        if m.get("klasse") == "Brondefinitie" or m.get("id") in gerefereerd
    ]
    brondefinities = [m for m in markeringen if m.get("klasse") == "Brondefinitie"]
    if brondefinities:
        uit["brondefinities"] = brondefinities
    gekoppeld = [m for m in markeringen if m.get("klasse") != "Brondefinitie"]
    if gekoppeld:
        uit["gekoppelde_markeringen"] = gekoppeld
    return uit


# --- main ---------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--rapport", required=True, type=Path,
                    help="pad naar het wetsanalyse-rapport.json")
    ap.add_argument("--out", required=True, type=Path,
                    help="pad naar het te schrijven ingest.json")
    args = ap.parse_args()

    if not args.rapport.exists():
        sys.exit(f"FOUT: rapport niet gevonden: {args.rapport}")

    rapport = laad_json(args.rapport)

    gerefereerd = gerefereerde_markering_ids(rapport)
    bronnen = [lichte_bron(b, gerefereerd) for b in (rapport.get("bronnen") or [])]
    begrippen = rapport.get("begrippen") or []
    afleidingsregels = rapport.get("afleidingsregels") or []

    if not bronnen:
        sys.exit("FOUT: rapport bevat geen bronnen.")

    ingest = {
        "werkgebied": rapport.get("werkgebied") or {},
        "bronnen": bronnen,
        "begrippen": begrippen,
        "afleidingsregels": afleidingsregels,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(ingest, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    print(f"ingest.json geschreven naar {args.out}")
    print(f"Bron: {args.rapport} "
          f"({len(bronnen)} bron(nen), {len(begrippen)} begrip(pen), "
          f"{len(afleidingsregels)} afleidingsregel(s))")

    # Referentiële integriteit: dezelfde controles als build_rapport_json.py, zodat
    # je vroeg ziet of de herkomst-keten klopt voordat je gaat formaliseren.
    bron_ids = {b.get("bron_id") for b in bronnen if b.get("bron_id")}
    verwijzing_ids = {
        v.get("id")
        for b in bronnen
        for v in (b.get("verwijzingen") or [])
        if v.get("id")
    }
    begrip_ids = {b.get("id") for b in begrippen if b.get("id")}
    problemen: list[str] = []

    def check_begrip_ref(enkelvoud: str, iid: str, veld: str, ref) -> None:
        if ref and ref not in begrip_ids:
            problemen.append(f"{enkelvoud} '{iid}' → onbekend begrip-id '{ref}' in {veld}")

    for groep, enkelvoud in (("begrippen", "begrip"), ("afleidingsregels", "afleidingsregel")):
        for item in ingest[groep]:
            iid = item.get("id", "?")
            bv = item.get("bron_verwijzing")
            if bv and bv not in verwijzing_ids:
                problemen.append(f"{enkelvoud} '{iid}' → onbekende bron_verwijzing '{bv}'")
            for vp in (item.get("vindplaatsen") or []):
                bid = vp.get("bron_id")
                if bid and bid not in bron_ids:
                    problemen.append(f"{enkelvoud} '{iid}' → onbekende vindplaats-bron_id '{bid}'")

    # Nieuwe begrip-id-velden: de regels zijn op begrip-id's gebouwd — een dangling id
    # breekt de herkomst-keten naar GegevensSpraak.
    for b in begrippen:
        iid = b.get("id", "?")
        for ref in (b.get("verwijst_naar_begrippen") or []):
            check_begrip_ref("begrip", iid, "verwijst_naar_begrippen", ref)
        for rel in (b.get("relaties") or []):
            if isinstance(rel, dict):
                check_begrip_ref("begrip", iid, "relaties.doel_begrip", rel.get("doel_begrip"))
    for r in afleidingsregels:
        iid = r.get("id", "?")
        uitvoer = r.get("uitvoer") or {}
        if isinstance(uitvoer, dict):
            check_begrip_ref("afleidingsregel", iid, "uitvoer", uitvoer.get("begrip_id"))
        for veld in ("invoer", "parameters"):
            for item in (r.get(veld) or []):
                if isinstance(item, dict):
                    check_begrip_ref("afleidingsregel", iid, veld, item.get("begrip_id"))
        for vw in (r.get("voorwaarden") or []):
            if isinstance(vw, dict):
                for ref in (vw.get("begrip_ids") or []):
                    check_begrip_ref("afleidingsregel", iid, "voorwaarden", ref)

    if problemen:
        print("Let op: dangling referenties (controleer het rapport):")
        for p in problemen:
            print(f"  - {p}")


if __name__ == "__main__":
    main()
