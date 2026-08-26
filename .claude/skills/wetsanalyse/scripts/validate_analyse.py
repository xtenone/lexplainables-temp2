#!/usr/bin/env python3
"""Pre-check van analyse.json vóór de review-server.

Controleert mechanische fouten zodat de menselijke review zich op inhoud kan richten.
Draai dit script na het schrijven van analyse.json, vóórdat je review_server.py start.

De analyse-eenheid is het **werkgebied** met meerdere **bronnen**: activiteit 2 draagt een
`bronnen[]`-array (per bron leden/markeringen/verwijzingen). Id's zijn werkgebied-breed uniek.

Exitcodes:
  0 — geen fouten of waarschuwingen
  1 — waarschuwingen (niet-blokkerend; toon als context bij de review)
  2 — fouten (blokkerend; herstel vóórdat je de review-server start)

Gebruik:
  python validate_analyse.py --input analyse.json --activiteit 2
"""

import argparse
import io
import json
import re
import sys
import unicodedata
from pathlib import Path

# De canonieke weergave-volgorde van de dertien JAS-klassen (docs/wetsanalyse/wa-table.png).
# Alle resultaatweergaves (viewers, Markdown-exports, frontend) sorteren hierop.
JAS_KLASSEN_VOLGORDE: tuple[str, ...] = (
    "Rechtssubject",
    "Rechtsobject",
    "Rechtsbetrekking",
    "Rechtsfeit",
    "Voorwaarde",
    "Afleidingsregel",
    "Variabele en variabelewaarde",
    "Parameter en parameterwaarde",
    "Operator",
    "Tijdsaanduiding",
    "Plaatsaanduiding",
    "Delegatiebevoegdheid en delegatie-invulling",
    "Brondefinitie",
)

GELDIGE_JAS_KLASSEN = set(JAS_KLASSEN_VOLGORDE)


def jas_sorteersleutel(klasse: str) -> int:
    """Sorteersleutel voor presentatie: klasse-index in de wa-table-volgorde;
    onbekende klassen achteraan. Gebruik met een stabiele sort zodat de onderlinge
    (document)volgorde binnen een klasse behouden blijft."""
    try:
        return JAS_KLASSEN_VOLGORDE.index(klasse)
    except ValueError:
        return len(JAS_KLASSEN_VOLGORDE)

# De labelkleuren per JAS-klasse uit de officiële JAS-tabel (docs/wetsanalyse/wa-table.png),
# per pixel gesampled: (achtergrond, rand). De rand is dezelfde kleur ~22% donkerder; de tekst is
# altijd #1A1A1A (≥ 5,4:1 op elke tint). Samengevoegde klassen nemen de hoofdkleur uit de tabel
# (Variabele / Parameter / Delegatiebevoegdheid).
#
# Dit is de CANONIEKE bron: de api leest hem in voor de PDF-export (api/app/validation.py) en
# frontend/lib/jas.ts draagt dezelfde waarden als Tailwind-klassen, bewaakt door een drift-test.
JAS_KLASSE_KLEUREN: dict[str, tuple[str, str]] = {
    "Rechtssubject": ("#d8eaf7", "#a8b6c0"),
    "Rechtsobject": ("#b2c3e3", "#8a98b1"),
    "Rechtsbetrekking": ("#90a2d0", "#707ea2"),
    "Rechtsfeit": ("#bad8f1", "#91a8bb"),
    "Voorwaarde": ("#b7d8cd", "#8ea89f"),
    "Afleidingsregel": ("#d47479", "#a55a5e"),
    "Variabele en variabelewaarde": ("#f5dc5e", "#bfab49"),
    "Parameter en parameterwaarde": ("#e6b8bb", "#b38f91"),
    "Operator": ("#d7e8e2", "#a7b4b0"),
    "Tijdsaanduiding": ("#cbb8d6", "#9e8fa6"),
    "Plaatsaanduiding": ("#e6d3e5", "#b3a4b2"),
    "Delegatiebevoegdheid en delegatie-invulling": ("#b0b1b2", "#898a8a"),
    "Brondefinitie": ("#edefef", "#b8baba"),
}

JAS_TEKSTKLEUR = "#1A1A1A"

GELDIGE_VERWIJZING_FUNCTIES = {
    "definitie", "schakel", "delegatie", "intra-artikel", "informatief",
}
GELDIGE_VERWIJZING_STATUS = {
    "opgehaald", "gevolgd", "gesignaleerd", "buiten-scope-diepte",
}
GELDIGE_VERWIJZING_SOORT = {"intref", "extref", "natuurlijk"}

DELEGATIE_KLASSE = "Delegatiebevoegdheid en delegatie-invulling"

# Een formulering markeert een niet altijd aaneengesloten stuk wettekst. De skill mag
# daarbij twee citeerconventies gebruiken die de letterlijke-substring-toets breken:
#   - beletselteken ('...' of '…') om weggelaten tussentekst te eliden;
#   - vierkante haken ([...]) om een verduidelijking/referent in te voegen.
# We toetsen daarom per losgesplitst fragment of het letterlijk in de wettekst staat,
# na verwijdering van de ingevoegde haken.
_ELLIPS = re.compile(r"\s*(?:\.\.\.|…)\s*")
_HAKEN = re.compile(r"\[[^\]]*\]")

# Lid-nummer uit een lid-relatieve vindplaats ("lid 2", "lid 3, onderdeel a", …).
_VINDPLAATS_LID = re.compile(r"\blid\s+(\S+?)[\s,.;]*(?:$|,)", re.IGNORECASE)


def _geclaimde_lid_tekst(vindplaats: str, leden: list[dict]) -> str | None:
    """De tekst van het lid dat `vindplaats` claimt, of None als er geen specifiek lid te
    herleiden is (geen lid-nummer, of het genoemde lid bestaat niet in de bron)."""
    m = _VINDPLAATS_LID.search(vindplaats or "")
    if not m:
        return None
    nummer = m.group(1).strip().rstrip(".,;")
    for lid in leden:
        if str(lid.get("lid") or "").strip() == nummer:
            return lid.get("tekst") or ""
    return None


def fragmenten_letterlijk(formulering: str, brontekst: str) -> bool:
    """True als elk (op beletselteken gesplitst) fragment letterlijk in de brontekst staat.

    Vierkante-haak-invoegingen worden eerst weggestript, zodat 'een [bankrekening]' op
    'een' wordt getoetst. Lege fragmenten (bv. door een eind-beletselteken) tellen niet mee,
    maar minstens ÉÉN niet-leeg letterlijk fragment is verplicht: een formulering die geheel
    uit invoegingen/beletseltekens bestaat ('[...]', '…') citeert niets en is dus geen citaat.

    Beide kanten worden eerst naar unicode-NFC genormaliseerd: zonder dat zouden een composé
    'é' (U+00E9) en een decomposé 'e'+combining-accent (U+0065 U+0301) — visueel identiek —
    als ongelijk gelden en een terecht citaat ten onrechte de toets laten falen.
    """
    formulering = unicodedata.normalize("NFC", formulering)
    brontekst = unicodedata.normalize("NFC", brontekst)
    schoon = _HAKEN.sub("", formulering)
    fragmenten = [f.strip() for f in _ELLIPS.split(schoon) if f.strip()]
    if not fragmenten:
        return False
    return all(f in brontekst for f in fragmenten)


def check_verwijzing_item(v: dict, geziene_ids: set[str], label: str) -> tuple[list[str], list[str]]:
    """Valideert één uitgaande verwijzing (structuur + enums). `geziene_ids` is werkgebied-breed."""
    fouten: list[str] = []
    waarschuwingen: list[str] = []

    vid = v.get("id", "")
    if not vid:
        fouten.append(f"[{label}] Verwijzing heeft geen 'id'.")
    else:
        if vid in geziene_ids:
            fouten.append(f"Verwijzing-id '{vid}' komt meerdere keren voor (werkgebied-breed).")
        geziene_ids.add(vid)

    functie = v.get("functie", "")
    if not functie:
        fouten.append(f"[{vid or '?'}] Verwijzing mist 'functie'.")
    elif functie not in GELDIGE_VERWIJZING_FUNCTIES:
        fouten.append(
            f"[{vid or '?'}] Ongeldige verwijzing-functie: '{functie}'. "
            f"Gebruik: {', '.join(sorted(GELDIGE_VERWIJZING_FUNCTIES))}."
        )

    status = v.get("status", "")
    if not status:
        fouten.append(f"[{vid or '?'}] Verwijzing mist 'status'.")
    elif status not in GELDIGE_VERWIJZING_STATUS:
        fouten.append(
            f"[{vid or '?'}] Ongeldige verwijzing-status: '{status}'. "
            f"Gebruik: {', '.join(sorted(GELDIGE_VERWIJZING_STATUS))}."
        )

    soort = v.get("soort", "")
    if soort and soort not in GELDIGE_VERWIJZING_SOORT:
        waarschuwingen.append(
            f"[{vid or '?'}] Onbekende verwijzing-soort: '{soort}' "
            f"(verwacht: {', '.join(sorted(GELDIGE_VERWIJZING_SOORT))})."
        )

    doel = v.get("doel") or {}
    if not (doel.get("label") or "").strip():
        fouten.append(f"[{vid or '?'}] Verwijzing mist 'doel.label'.")

    return fouten, waarschuwingen


def check_activiteit_2(data: dict) -> tuple[list[str], list[str]]:
    fouten: list[str] = []
    waarschuwingen: list[str] = []

    bronnen = data.get("bronnen") or []
    if not bronnen:
        fouten.append("Geen bronnen in 'bronnen' (een werkgebied heeft minstens één bron).")

    geziene_ids: set[str] = set()   # werkgebied-breed: markeringen én verwijzingen
    bron_ids: set[str] = set()
    heeft_delegatie_markering = False
    heeft_delegatie_verwijzing = False

    for bron in bronnen:
        bron_id = bron.get("bron_id", "")
        label = bron.get("label") or bron_id or "?"
        if not bron_id:
            fouten.append("Bron heeft geen 'bron_id'.")
        elif bron_id in bron_ids:
            fouten.append(f"bron_id '{bron_id}' komt meerdere keren voor.")
        else:
            bron_ids.add(bron_id)

        if not (bron.get("bronreferentie") or "").strip():
            fouten.append(f"[{label}] Veld 'bronreferentie' ontbreekt of is leeg.")

        leden_tekst = " ".join(
            (lid.get("tekst") or "") for lid in (bron.get("leden") or [])
        )

        markeringen = bron.get("markeringen") or []
        if not markeringen:
            waarschuwingen.append(f"[{label}] Geen markeringen gevonden.")

        for m in markeringen:
            mid = m.get("id", "")
            if not mid:
                fouten.append(f"[{label}] Markering heeft geen 'id' (verplicht voor feedback-koppeling).")
            else:
                if mid in geziene_ids:
                    fouten.append(f"Id '{mid}' komt meerdere keren voor (werkgebied-breed).")
                geziene_ids.add(mid)

            m_bron = m.get("bron_id", "")
            if m_bron and bron_id and m_bron != bron_id:
                fouten.append(
                    f"[{mid or '?'}] bron_id '{m_bron}' wijkt af van de bron '{bron_id}' "
                    "waarin de markering staat."
                )

            klasse = m.get("klasse", "")
            if not klasse:
                fouten.append(f"[{mid or '?'}] Veld 'klasse' ontbreekt of is leeg.")
            elif klasse not in GELDIGE_JAS_KLASSEN:
                fouten.append(
                    f"[{mid or '?'}] Ongeldige JAS-klasse: '{klasse}'. "
                    "Gebruik een van de 13 toegestane klassen."
                )
            elif klasse == DELEGATIE_KLASSE:
                heeft_delegatie_markering = True

            formulering = (m.get("formulering") or "").strip()
            if formulering and leden_tekst:
                # Toets tegen het lid dat de vindplaats claimt; alleen zonder herleidbaar lid
                # valt de toets terug op de samengevoegde leden-tekst. Een citaat-mismatch is
                # blokkerend (fout): brongetrouwheid is niet onderhandelbaar.
                doel_tekst = _geclaimde_lid_tekst(m.get("vindplaats") or "", bron.get("leden") or [])
                if doel_tekst is None:
                    doel_tekst = leden_tekst
                if not fragmenten_letterlijk(formulering, doel_tekst):
                    kort = formulering[:60] + ("..." if len(formulering) > 60 else "")
                    fouten.append(
                        f"[{mid}] Formulering lijkt geen letterlijk citaat uit de wettekst "
                        f"van de geclaimde vindplaats: '{kort}'"
                    )

            if not (m.get("vindplaats") or "").strip():
                waarschuwingen.append(f"[{mid}] Veld 'vindplaats' ontbreekt of is leeg.")

        for v in (bron.get("verwijzingen") or []):
            v_bron = v.get("bron_id", "")
            if v_bron and bron_id and v_bron != bron_id:
                fouten.append(
                    f"[{v.get('id', '?')}] verwijzing-bron_id '{v_bron}' wijkt af van bron "
                    f"'{bron_id}'."
                )
            if v.get("functie") == "delegatie":
                heeft_delegatie_verwijzing = True
            v_fouten, v_waarschuwingen = check_verwijzing_item(v, geziene_ids, label)
            fouten.extend(v_fouten)
            waarschuwingen.extend(v_waarschuwingen)

    # Delegatie-koppeling: een delegatie-markering hoort ergens in het werkgebied een verwijzing
    # met functie 'delegatie' te hebben (de gedelegeerde regeling als uitgaande pointer of een
    # eigen bron).
    if heeft_delegatie_markering and not heeft_delegatie_verwijzing:
        waarschuwingen.append(
            "Er is een markering met klasse 'Delegatiebevoegdheid en delegatie-invulling' "
            "maar geen verwijzing met functie 'delegatie' — leg de gedelegeerde regeling "
            "vast als verwijzing of als eigen bron."
        )

    return fouten, waarschuwingen


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Pre-check analyse.json voor review")
    parser.add_argument("--input", type=Path, required=True,
                        help="Pad naar analyse.json")
    parser.add_argument("--activiteit", choices=["2"], default="2",
                        help="Activiteit 2 (de enige activiteit in scope)")
    args = parser.parse_args()

    def _lees_json(pad: Path, label: str) -> dict:
        if not pad.exists():
            print(f"FOUT: {label} niet gevonden: {pad}", file=sys.stderr)
            sys.exit(2)
        try:
            return json.loads(pad.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"FOUT: ongeldige JSON in {pad}: {e}", file=sys.stderr)
            sys.exit(2)

    data = _lees_json(args.input, "bestand")

    fouten, waarschuwingen = check_activiteit_2(data)
    context = f"{len(data.get('bronnen') or [])} bron(nen)"

    print(f"\n  Pre-check analyse.json - activiteit {args.activiteit}, werkgebied {context}")
    print(f"  {'-' * 52}")

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
