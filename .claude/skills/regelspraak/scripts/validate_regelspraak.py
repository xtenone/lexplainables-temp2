#!/usr/bin/env python3
"""Pre-check van een regelspraak-model.json vóór de review-server.

Controleert mechanische fouten zodat de menselijke review zich op inhoud kan richten.
Draai dit na het schrijven van model.json, vóórdat je review_server.py start.

Twee stappen:
  - `gegevensspraak`: het objectmodel (objecttypen, attributen, kenmerken, domeinen,
    parameters, feittypen/rollen, eenheidssystemen, dimensies, tijdlijnen, dagsoorten).
  - `regels`: de RegelSpraak-regels (+ een lichte gegevensspraak_index om naar te verwijzen).

Exitcodes:
  0 — geen fouten of waarschuwingen
  1 — waarschuwingen (niet-blokkerend; toon als context bij de review)
  2 — fouten (blokkerend; herstel vóórdat je de review-server start)

Gebruik:
  python validate_regelspraak.py --input model.json --stap gegevensspraak|regels
"""

import argparse
import io
import json
import re
import sys
from pathlib import Path

GELDIGE_KENMERK_SOORTEN = {"bijvoeglijk", "bezittelijk", "overig"}
GELDIGE_MULTIPLICITEIT = {"een", "meerdere"}
GELDIGE_REGELSOORTEN = {
    "gelijkstelling", "kenmerktoekenning", "consistentieregel", "initialisatie",
    "objectcreatie", "feitcreatie", "verdeling", "dagsoortdefinitie", "startpuntbepaling",
}

# Standaarddatatypes (RegelSpraak v2.3.0 §3.3). Een datatype mag ook een domeinnaam zijn;
# dat checken we apart tegen de gedeclareerde domeinen.
STANDAARD_DATATYPE_PREFIX = ("Numeriek", "Tekst", "Boolean", "Datum", "Percentage")

# Veel-gehallucineerde "operatoren" die niet in RegelSpraak bestaan. Puur een waarschuwing:
# de echte operatoren zijn plus / min / verminderd met / maal / gedeeld door / de som van / …
# (zie expressies-en-operatoren-referentie.md). Sleutel = verdacht patroon, waarde = hint.
VERDACHTE_PATRONEN = {
    r"\bvermeerderd met\b": "gebruik 'plus' (optellen bestaat niet als 'vermeerderd met')",
    r"\bopgeteld bij\b": "gebruik 'plus'",
    r"\bafgetrokken van\b": "gebruik 'min' of 'verminderd met'",
    r"\bvermenigvuldigd met\b": "gebruik 'maal'",
    r"\bgedeeld op\b": "gebruik 'gedeeld door'",
    r"(?<!de )\bsom van\b": "sommatie is 'de som van'",
}


def heeft_herkomst(item: dict) -> bool:
    h = item.get("herkomst") or {}
    if not isinstance(h, dict):
        return False
    heeft_ref = bool(h.get("begrip_ids") or h.get("regel_id") or h.get("bron_id"))
    heeft_vp = bool(h.get("vindplaatsen"))
    return heeft_ref or heeft_vp


def _verzamel_uit_herkomst(h: dict, begrip_ids: set, regel_ids: set, bron_ids: set) -> None:
    if not isinstance(h, dict):
        return
    for bid in (h.get("begrip_ids") or []):
        if bid:
            begrip_ids.add(bid)
    if h.get("regel_id"):
        regel_ids.add(h["regel_id"])
    for vp in (h.get("vindplaatsen") or []):
        if isinstance(vp, dict) and vp.get("bron_id"):
            bron_ids.add(vp["bron_id"])


def verzamel_herkomst_refs(obj) -> tuple[set, set, set]:
    """Loop recursief door obj en oogst álle herkomst-referenties.

    Node-agnostisch: pakt elke `herkomst` ongeacht het knooptype (objecttype, parameter,
    feittype, regel, of een geneste attribuut/kenmerk dat er een draagt). Zo is de check
    robuust tegen schemavarianten en mist hij geen herkomst die dieper genest staat.
    Geeft (begrip_ids, regel_ids, bron_ids) terug.
    """
    begrip_ids: set[str] = set()
    regel_ids: set[str] = set()
    bron_ids: set[str] = set()

    def loop(node) -> None:
        if isinstance(node, dict):
            if "herkomst" in node:
                _verzamel_uit_herkomst(node.get("herkomst") or {}, begrip_ids, regel_ids, bron_ids)
            for v in node.values():
                loop(v)
        elif isinstance(node, list):
            for item in node:
                loop(item)

    loop(obj)
    return begrip_ids, regel_ids, bron_ids


def regel_gerefereerde_begrip_ids(ingest: dict) -> set:
    """Alle begrip-id's waar een ingest-afleidingsregel op steunt (uitvoer/invoer/parameters/
    voorwaarden) — die begrippen MOETEN in GegevensSpraak gedekt zijn, anders kan de regels-stap
    de id-koppeling niet leggen."""
    ids: set = set()
    for r in (ingest.get("afleidingsregels") or []):
        uitvoer = r.get("uitvoer") or {}
        if isinstance(uitvoer, dict) and uitvoer.get("begrip_id"):
            ids.add(uitvoer["begrip_id"])
        for veld in ("invoer", "parameters"):
            for item in (r.get(veld) or []):
                if isinstance(item, dict) and item.get("begrip_id"):
                    ids.add(item["begrip_id"])
        for vw in (r.get("voorwaarden") or []):
            if isinstance(vw, dict):
                ids.update(x for x in (vw.get("begrip_ids") or []) if x)
    return ids


def check_ingest(data: dict, stap: str, ingest: dict) -> tuple[list[str], list[str]]:
    """Toets de herkomst-keten van het model tegen de wetsanalyse-ingest.

    Twee richtingen (zie review-checkpoints.md):
      - integriteit (blokkerend): elke herkomst-referentie (begrip-/regel-/bron-id) moet in de
        ingest bestaan — een verschoven of verzonnen id breekt de traceerbaarheid;
      - dekking (waarschuwing): elk ingest-begrip (stap gegevensspraak) resp. elke ingest-regel
        (stap regels) moet ergens herkomst krijgen, anders is het stil uit de vertaling gevallen.
    """
    fouten: list[str] = []
    waarschuwingen: list[str] = []

    begrip_namen = {b.get("id"): b.get("naam") for b in (ingest.get("begrippen") or []) if b.get("id")}
    regel_namen = {r.get("id"): r.get("naam") for r in (ingest.get("afleidingsregels") or []) if r.get("id")}
    ingest_begrip_ids = set(begrip_namen)
    ingest_regel_ids = set(regel_namen)
    ingest_bron_ids = {b.get("bron_id") for b in (ingest.get("bronnen") or []) if b.get("bron_id")}

    scope = (data.get("gegevensspraak") or {}) if stap == "gegevensspraak" \
        else {"regels": data.get("regels") or []}
    ref_begrip_ids, ref_regel_ids, ref_bron_ids = verzamel_herkomst_refs(scope)

    # Integriteit (blokkerend).
    for bid in sorted(ref_begrip_ids - ingest_begrip_ids):
        fouten.append(
            f"Herkomst verwijst naar begrip-id '{bid}' dat niet in de wetsanalyse (ingest) bestaat."
        )
    for rid in sorted(ref_regel_ids - ingest_regel_ids):
        fouten.append(
            f"Herkomst verwijst naar afleidingsregel-id '{rid}' dat niet in de wetsanalyse (ingest) bestaat."
        )
    for brid in sorted(ref_bron_ids - ingest_bron_ids):
        fouten.append(
            f"Herkomst-vindplaats verwijst naar bron-id '{brid}' dat niet in de wetsanalyse (ingest) bestaat."
        )

    # Dekking (waarschuwing): per stap de bijbehorende ingest-as. Een begrip waar een
    # afleidingsregel op steunt krijgt een scherpere melding — zonder declaratie kan de
    # regels-stap de begrip-id-koppeling (uitvoer/invoer/parameters/voorwaarden) niet leggen.
    if stap == "gegevensspraak":
        regel_refs = regel_gerefereerde_begrip_ids(ingest)
        for bid in sorted(ingest_begrip_ids - ref_begrip_ids):
            naam = f" ({begrip_namen[bid]})" if begrip_namen.get(bid) else ""
            if bid in regel_refs:
                waarschuwingen.append(
                    f"Begrip '{bid}'{naam} wordt door een afleidingsregel gerefereerd maar door "
                    "geen enkele GegevensSpraak-declaratie gedekt — de regels-stap kan de "
                    "begrip-id-koppeling dan niet leggen."
                )
            else:
                waarschuwingen.append(
                    f"Begrip '{bid}'{naam} uit de wetsanalyse wordt door geen enkele declaratie gedekt "
                    "— gedekt elders, of bewust buiten scope (validatiepunt)?"
                )
    else:
        for rid in sorted(ingest_regel_ids - ref_regel_ids):
            naam = f" ({regel_namen[rid]})" if regel_namen.get(rid) else ""
            waarschuwingen.append(
                f"Afleidingsregel '{rid}'{naam} uit de wetsanalyse wordt door geen enkele regel gedekt "
                "— gedekt, of bewust buiten scope (validatiepunt)?"
            )

    return fouten, waarschuwingen


def check_regelspraak_tekst(tekst: str, iid: str) -> list[str]:
    """Waarschuw bij verdachte, niet-bestaande taalpatronen in de RegelSpraak-tekst."""
    waarschuwingen: list[str] = []
    for patroon, hint in VERDACHTE_PATRONEN.items():
        if re.search(patroon, tekst, flags=re.IGNORECASE):
            waarschuwingen.append(
                f"[{iid or '?'}] Verdacht taalpatroon in regelspraak_tekst — {hint}."
            )
    return waarschuwingen


def check_gegevensspraak(data: dict) -> tuple[list[str], list[str]]:
    fouten: list[str] = []
    waarschuwingen: list[str] = []

    gs = data.get("gegevensspraak") or {}
    if not gs:
        fouten.append("Geen 'gegevensspraak'-object gevonden.")
        return fouten, waarschuwingen

    geziene_ids: set[str] = set()
    domeinnamen = {d.get("naam") for d in (gs.get("domeinen") or []) if d.get("naam")}
    objecttype_namen = {o.get("naam") for o in (gs.get("objecttypen") or []) if o.get("naam")}

    def registreer_id(iid: str, soort: str, label: str) -> None:
        if not iid:
            fouten.append(f"[{label}] {soort} heeft geen 'id' (verplicht voor feedback-koppeling).")
        else:
            if iid in geziene_ids:
                fouten.append(f"Id '{iid}' komt meerdere keren voor (werkgebied-breed).")
            geziene_ids.add(iid)

    objecttypen = gs.get("objecttypen") or []
    if not objecttypen:
        waarschuwingen.append("Geen objecttypen in de GegevensSpraak.")

    for o in objecttypen:
        naam = o.get("naam") or "?"
        registreer_id(o.get("id", ""), "Objecttype", naam)
        if not (o.get("naam") or "").strip():
            fouten.append("Objecttype heeft geen 'naam'.")
        if not heeft_herkomst(o):
            waarschuwingen.append(f"[{naam}] Objecttype mist 'herkomst' (begrip-id + vindplaatsen).")
        if not (o.get("regelspraak_tekst") or "").strip():
            waarschuwingen.append(f"[{naam}] Objecttype mist 'regelspraak_tekst'.")

        for a in (o.get("attributen") or []):
            an = a.get("naam") or "?"
            dt = (a.get("datatype") or "").strip()
            if not dt:
                fouten.append(f"[{naam}.{an}] Attribuut mist 'datatype' (of domein).")
            elif not dt.startswith(STANDAARD_DATATYPE_PREFIX) and dt not in domeinnamen:
                waarschuwingen.append(
                    f"[{naam}.{an}] Datatype '{dt}' is geen standaarddatatype en geen "
                    "gedeclareerd domein."
                )

        for k in (o.get("kenmerken") or []):
            kn = k.get("naam") or "?"
            soort = (k.get("soort") or "").strip()
            if soort and soort not in GELDIGE_KENMERK_SOORTEN:
                fouten.append(
                    f"[{naam}.{kn}] Ongeldige kenmerk-soort: '{soort}'. "
                    f"Gebruik: {', '.join(sorted(GELDIGE_KENMERK_SOORTEN))}."
                )

    for d in (gs.get("domeinen") or []):
        if not (d.get("regelspraak_tekst") or "").strip():
            waarschuwingen.append(f"[{d.get('naam', '?')}] Domein mist 'regelspraak_tekst'.")

    for p in (gs.get("parameters") or []):
        pn = p.get("naam") or "?"
        registreer_id(p.get("id", ""), "Parameter", pn)
        if not (p.get("datatype") or "").strip():
            fouten.append(f"[{pn}] Parameter mist 'datatype' (of domein).")
        if not heeft_herkomst(p):
            waarschuwingen.append(f"[{pn}] Parameter mist 'herkomst'.")

    for ft in (gs.get("feittypen") or []):
        fn = ft.get("naam") or "?"
        registreer_id(ft.get("id", ""), "Feittype", fn)
        rollen = ft.get("rollen") or []
        if len(rollen) < 1:
            fouten.append(f"[{fn}] Feittype heeft geen rollen.")
        for rol in rollen:
            rn = rol.get("naam") or "?"
            mult = (rol.get("multipliciteit") or "").strip()
            if mult and mult not in GELDIGE_MULTIPLICITEIT:
                fouten.append(
                    f"[{fn}.{rn}] Ongeldige rol-multipliciteit: '{mult}'. "
                    f"Gebruik: {', '.join(sorted(GELDIGE_MULTIPLICITEIT))}."
                )
            ot = (rol.get("objecttype") or "").strip()
            if ot and objecttype_namen and ot not in objecttype_namen:
                waarschuwingen.append(
                    f"[{fn}.{rn}] Rol verwijst naar objecttype '{ot}' dat niet in de "
                    "GegevensSpraak is gedeclareerd."
                )

    return fouten, waarschuwingen


def check_regels(data: dict) -> tuple[list[str], list[str]]:
    fouten: list[str] = []
    waarschuwingen: list[str] = []

    regels = data.get("regels") or []
    if not regels:
        fouten.append("Geen 'regels' gevonden.")

    index = data.get("gegevensspraak_index") or {}
    bekende_objecttypen = {o.get("naam") for o in (index.get("objecttypen") or []) if o.get("naam")}
    bekende_parameters = {p.get("naam") for p in (index.get("parameters") or []) if p.get("naam")}
    if not index:
        waarschuwingen.append(
            "Geen 'gegevensspraak_index' — de regels kunnen niet tegen het objectmodel "
            "worden getoetst."
        )

    geziene_ids: set[str] = set()
    geziene_namen: set[str] = set()
    alle_teksten: list[str] = []

    for r in regels:
        rid = r.get("id", "")
        naam = (r.get("naam") or "").strip()
        if not rid:
            fouten.append("Regel heeft geen 'id' (verplicht voor feedback-koppeling).")
        else:
            if rid in geziene_ids:
                fouten.append(f"Regel-id '{rid}' komt meerdere keren voor.")
            geziene_ids.add(rid)

        if not naam:
            fouten.append(f"[{rid or '?'}] Regel heeft geen 'naam'.")
        elif naam in geziene_namen:
            fouten.append(f"[{rid or '?'}] Regelnaam '{naam}' is niet uniek.")
        else:
            geziene_namen.add(naam)

        soort = (r.get("soort") or "").strip()
        if not soort:
            waarschuwingen.append(f"[{rid or '?'}] Regel mist 'soort' (resultaatactie).")
        elif soort not in GELDIGE_REGELSOORTEN:
            fouten.append(
                f"[{rid or '?'}] Ongeldige regel-soort: '{soort}'. "
                f"Gebruik een van: {', '.join(sorted(GELDIGE_REGELSOORTEN))}."
            )

        tekst = (r.get("regelspraak_tekst") or "").strip()
        if not tekst:
            fouten.append(f"[{rid or '?'}] Regel mist 'regelspraak_tekst'.")
        else:
            alle_teksten.append(tekst)
            if not re.search(r"^\s*Regel\b", tekst):
                waarschuwingen.append(f"[{rid or '?'}] regelspraak_tekst begint niet met 'Regel'.")
            if not re.search(r"\bgeldig\b", tekst):
                waarschuwingen.append(
                    f"[{rid or '?'}] regelspraak_tekst mist een 'geldig'-regelversie."
                )
            waarschuwingen.extend(check_regelspraak_tekst(tekst, rid))

        if not heeft_herkomst(r):
            waarschuwingen.append(f"[{rid or '?'}] Regel mist 'herkomst' (regel-id + vindplaatsen).")

    # Gebruik-scan tegen het objectmodel: een gedeclareerde parameter/objecttype dat door geen
    # enkele regel wordt aangeroepen, is een signaal dat er een regel ontbreekt (de meest
    # voorkomende fout: termijn-parameters wel declareren, maar de rekenregel die ze consumeert
    # niet schrijven). Alleen zinvol als er een index én regelteksten zijn.
    #
    # Matching is een bewust conservatieve heuristiek: case-insensitive substring van de volledige
    # gedeclareerde naam in enige regelspraak_tekst. False-negatives bij afkorting/herformulering
    # zijn acceptabel — dit is een waarschuwing, geen blokkerende fout (een gedeeld objectmodel
    # mag breder zijn dan deze set regels).
    #
    # Buiten scope (geen betrouwbare statische check zonder expressie-parser): eenheid-/
    # datatype-mismatch tussen een expressie en het resultaat-attribuut (bv. een maandentelling
    # die naar een jaartal-attribuut wordt geschreven), en het strikt resolven van élke verwijzing
    # in de vrije regeltekst. Die blijven een review-/validatiepunt-zaak.
    if index and alle_teksten:
        corpus = "\n".join(alle_teksten).lower()
        for pnaam in sorted(n for n in bekende_parameters if n):
            if pnaam.lower() not in corpus:
                waarschuwingen.append(
                    f"Parameter '{pnaam}' is gedeclareerd maar wordt door geen regel gebruikt "
                    "(ontbreekt er een regel, of moet de parameter weg?)."
                )
        for onaam in sorted(n for n in bekende_objecttypen if n):
            if onaam.lower() not in corpus:
                waarschuwingen.append(
                    f"Objecttype '{onaam}' is gedeclareerd maar wordt door geen regel gebruikt."
                )

    return fouten, waarschuwingen


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Pre-check regelspraak-model.json voor review")
    parser.add_argument("--input", type=Path, required=True, help="Pad naar model.json")
    parser.add_argument("--stap", choices=["gegevensspraak", "regels"], required=True,
                        help="Welke stap wordt gevalideerd")
    parser.add_argument("--ingest", type=Path, default=None,
                        help="optioneel: wetsanalyse-ingest.json voor de herkomst-cross-check "
                             "(rapport-pad). Dangling herkomst = fout; ongedekte ingest = waarschuwing.")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"FOUT: bestand niet gevonden: {args.input}", file=sys.stderr)
        sys.exit(2)

    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"FOUT: ongeldige JSON in {args.input}: {e}", file=sys.stderr)
        sys.exit(2)

    if args.stap == "gegevensspraak":
        fouten, waarschuwingen = check_gegevensspraak(data)
        gs = data.get("gegevensspraak") or {}
        context = f"{len(gs.get('objecttypen') or [])} objecttype(n)"
    else:
        fouten, waarschuwingen = check_regels(data)
        context = f"{len(data.get('regels') or [])} regel(s)"

    # Optionele herkomst-cross-check tegen de wetsanalyse-ingest (rapport-pad).
    if args.ingest is not None:
        if not args.ingest.exists():
            fouten.append(f"--ingest opgegeven maar niet gevonden: {args.ingest}")
        else:
            try:
                ingest = json.loads(args.ingest.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                fouten.append(f"--ingest bevat ongeldige JSON ({args.ingest}): {e}")
            else:
                i_fouten, i_waarschuwingen = check_ingest(data, args.stap, ingest)
                fouten.extend(i_fouten)
                waarschuwingen.extend(i_waarschuwingen)

    werkgebied = (data.get("werkgebied") or {}).get("naam", "?")
    print(f"\n  Pre-check model.json - stap {args.stap}, werkgebied {werkgebied} ({context})")
    print(f"  {'-' * 56}")

    if not fouten and not waarschuwingen:
        print("  Geen fouten of waarschuwingen gevonden.\n")
        sys.exit(0)

    if fouten:
        print("\n  FOUTEN (blokkerend — herstel vóórdat je de review-server start):")
        for f in fouten:
            print(f"    FOUT  {f}")

    if waarschuwingen:
        print("\n  Waarschuwingen (niet-blokkerend — toon als context bij de review):")
        for w in waarschuwingen:
            print(f"    WAARSCHUWING  {w}")

    print()
    sys.exit(2 if fouten else 1)


if __name__ == "__main__":
    main()
