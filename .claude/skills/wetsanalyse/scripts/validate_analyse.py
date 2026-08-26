#!/usr/bin/env python3
"""Pre-check van analyse.json vóór de review-server.

Controleert mechanische fouten zodat de menselijke review zich op inhoud kan richten.
Draai dit script na het schrijven van analyse.json, vóórdat je review_server.py start.

De analyse-eenheid is het **werkgebied** met meerdere **bronnen**: activiteit 2 draagt een
`bronnen[]`-array (per bron leden/markeringen/verwijzingen); activiteit 3 is werkgebied-breed
(gedeelde begrippen/afleidingsregels met `vindplaatsen[{bron_id,lid}]`). Id's zijn
werkgebied-breed uniek.

Exitcodes:
  0 — geen fouten of waarschuwingen
  1 — waarschuwingen (niet-blokkerend; toon als context bij de review)
  2 — fouten (blokkerend; herstel vóórdat je de review-server start)

Gebruik:
  python validate_analyse.py --input analyse.json --activiteit 2|3
  # activiteit 3, met dekkingscheck tegen act-2 en herkomst-check tegen een aangeleverde lijst:
  python validate_analyse.py --input act3.json --activiteit 3 \
      --act2 act2.json --begrippenlijst begrippenlijst.json
"""

import argparse
import io
import json
import re
import sys
import unicodedata
from pathlib import Path

# De canonieke weergave-volgorde van de dertien JAS-klassen (docs/wa-table.png).
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

GELDIGE_REGELTYPEN = {"beslisregel", "rekenregel", "specialisatieregel"}

# Markeringen van deze klassen horen via `markering_ids` in ≥1 begrip te landen (dekking
# act 2 → act 3). Afleidingsregel-markeringen landen in ≥1 afleidingsregel. De overige
# klassen (Voorwaarde, Operator, Tijds-/Plaatsaanduiding, Delegatie, Brondefinitie) zijn
# niet begrip-plichtig: die landen in regel-voorwaarden, definities of verwijzingen.
BEGRIP_PLICHTIGE_KLASSEN = {
    "Rechtssubject",
    "Rechtsobject",
    "Rechtsbetrekking",
    "Rechtsfeit",
    "Variabele en variabelewaarde",
    "Parameter en parameterwaarde",
}

GELDIGE_HERKOMST_STATUS = {"hergebruikt", "aangepast", "nieuw"}
GELDIGE_RELATIE_SOORT = {"relatie", "kenmerk"}
GELDIGE_VERBINDING = {"EN", "OF", ""}

# Begripsnamen beginnen niet met een lidwoord of ontkenning (methode: begrippen zijn de
# bouwstenen voor afleidingsregels; taalpatronen leveren de lidwoorden/ontkenningen).
_NAAM_VERBODEN_START = ("de ", "het ", "een ", "geen ", "niet ")

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


def check_vindplaatsen(item: dict, iid: str, soort: str, bron_ids: set[str]) -> list[str]:
    """Waarschuw als 'vindplaatsen' ontbreekt/leeg is, items zonder bron_id bevat, of
    naar een bron_id wijst die niet in de bron-index staat."""
    waarschuwingen: list[str] = []
    vindplaatsen = item.get("vindplaatsen") or []
    if not vindplaatsen:
        waarschuwingen.append(f"[{iid or '?'}] {soort} heeft geen 'vindplaatsen'.")
    else:
        for vp in vindplaatsen:
            bid = (vp.get("bron_id") or "").strip()
            if not bid:
                waarschuwingen.append(f"[{iid or '?'}] vindplaats zonder 'bron_id'.")
            elif bron_ids and bid not in bron_ids:
                waarschuwingen.append(
                    f"[{iid or '?'}] vindplaats-bron_id '{bid}' staat niet in de bron-index."
                )
    return waarschuwingen


def _norm_naam(naam: str) -> str:
    """Genormaliseerde vorm voor naam-uniciteit: NFC, lowercase, samengevouwen whitespace."""
    return " ".join(unicodedata.normalize("NFC", naam).lower().split())


def _lijkt_werkwoordsvorm(naam: str) -> bool:
    """Heuristiek: begint de (regel)naam met een actieve werkwoordsvorm (infinitief op -en)?"""
    eerste = naam.strip().split()[0].lower() if naam.strip() else ""
    return len(eerste) > 3 and eerste.endswith("en")


def _act2_markeringen(act2: dict | None) -> dict[str, str]:
    """Markering-id → klasse over alle bronnen van de act-2-analyse."""
    index: dict[str, str] = {}
    for bron in ((act2 or {}).get("bronnen") or []):
        for m in (bron.get("markeringen") or []):
            if m.get("id"):
                index[m["id"]] = m.get("klasse", "")
    return index


def _object_items(
    item: dict, veld: str, iid: str, soort: str, fouten: list[str],
) -> list[dict]:
    """Lijstveld dat objecten hoort te bevatten: niet-objecten worden een schemafout
    (bv. oud-schema strings) in plaats van een crash; de rest wordt teruggegeven."""
    waarde = item.get(veld) or []
    if not isinstance(waarde, list):
        fouten.append(
            f"[{iid or '?'}] {soort}: '{veld}' is geen lijst — verwacht een lijst van objecten."
        )
        return []
    goede: list[dict] = []
    for x in waarde:
        if isinstance(x, dict):
            goede.append(x)
        else:
            fouten.append(
                f"[{iid or '?'}] {soort}: '{veld}' bevat een item dat geen object is "
                "(oud schema met vrije tekst? — gebruik de gestructureerde vorm)."
            )
    return goede


def _check_begrip_refs(
    item: dict, iid: str, soort: str, veld: str, begrip_ids: set[str], refs: list[str],
) -> list[str]:
    """Fouten voor referenties naar niet-bestaande begrip-id's."""
    fouten: list[str] = []
    for ref in refs:
        if ref and ref not in begrip_ids:
            fouten.append(
                f"[{iid or '?'}] {soort}: '{veld}' verwijst naar onbekend begrip-id '{ref}'."
            )
    return fouten


def check_activiteit_3(
    data: dict,
    act2: dict | None = None,
    begrippenlijst: dict | None = None,
) -> tuple[list[str], list[str]]:
    fouten: list[str] = []
    waarschuwingen: list[str] = []

    geziene_ids: set[str] = set()
    bron_ids = {b.get("bron_id") for b in (data.get("bronnen") or []) if b.get("bron_id")}

    begrippen = data.get("begrippen") or []
    regels = data.get("afleidingsregels") or []

    # Pre-pass: alle begrip-id's (voor dangling-checks) + genormaliseerde naam-index.
    begrip_ids = {b.get("id") for b in begrippen if b.get("id")}
    naam_index: dict[str, str] = {}   # genormaliseerde naam → begrip-id

    markering_index = _act2_markeringen(act2)
    gedekte_markeringen: set[str] = set()

    aangeleverde_ids = {
        b.get("id") for b in ((begrippenlijst or {}).get("begrippen") or []) if b.get("id")
    }

    for b in begrippen:
        bid = b.get("id", "")
        if not bid:
            fouten.append("Begrip heeft geen 'id' (verplicht voor feedback-koppeling).")
        else:
            if bid in geziene_ids:
                fouten.append(f"Id '{bid}' komt meerdere keren voor (begrip of afleidingsregel).")
            geziene_ids.add(bid)

        naam = (b.get("naam") or "").strip()
        if not naam:
            fouten.append(f"[{bid or '?'}] Begrip heeft geen 'naam'.")
        else:
            norm = _norm_naam(naam)
            if norm in naam_index:
                fouten.append(
                    f"[{bid or '?'}] Begripsnaam '{naam}' is niet uniek "
                    f"(botst met begrip '{naam_index[norm]}'). De voorkeursterm is uniek "
                    "per werkgebied — voeg samen (synoniemen) of splits met een "
                    "onderscheidende naam (homoniemen)."
                )
            else:
                naam_index[norm] = bid or "?"

            if naam.lower().startswith(_NAAM_VERBODEN_START):
                waarschuwingen.append(
                    f"[{bid or '?'}] Begripsnaam '{naam}' begint met een lidwoord of "
                    "ontkenning — laat dat weg (naamgevings-vuistregel)."
                )

        # Synoniemen delen de naamruimte met de voorkeurstermen: een synoniem dat samenvalt
        # met de naam (of een synoniem) van een ánder begrip is een botsing — dan zijn het
        # geen synoniemen maar een niet-ontdubbeld begrip of een niet-gesplitst homoniem.
        for syn in (b.get("synoniemen") or []):
            syn_norm = _norm_naam(str(syn))
            if not syn_norm:
                continue
            if naam and syn_norm == _norm_naam(naam):
                waarschuwingen.append(
                    f"[{bid or '?'}] Synoniem '{syn}' is gelijk aan de eigen begripsnaam — "
                    "laat het weg."
                )
                continue
            if syn_norm in naam_index and naam_index[syn_norm] != (bid or "?"):
                fouten.append(
                    f"[{bid or '?'}] Synoniem '{syn}' botst met begrip "
                    f"'{naam_index[syn_norm]}' (naam of synoniem). Voeg samen (synoniemen) "
                    "of splits met een onderscheidende naam (homoniemen)."
                )
            else:
                naam_index[syn_norm] = bid or "?"

        klasse = b.get("klasse", "")
        if not klasse:
            waarschuwingen.append(f"[{bid or '?'}] Veld 'klasse' ontbreekt of is leeg.")
        elif klasse not in GELDIGE_JAS_KLASSEN:
            # Fout (blokkerend), net als bij een act-2-markering: er zijn dertien JAS-klassen,
            # een verzonnen klasse op een begrip is net zo min toegestaan als op een markering.
            fouten.append(
                f"[{bid or '?'}] Klasse op begrip is geen geldige JAS-klasse: '{klasse}'. "
                "Gebruik een van de 13 toegestane klassen."
            )

        definitie = (b.get("definitie") or "").strip()
        if not definitie:
            waarschuwingen.append(f"[{bid or '?'}] Begrip heeft geen 'definitie'.")
        elif naam and _norm_naam(naam) in _norm_naam(definitie):
            waarschuwingen.append(
                f"[{bid or '?'}] De begripsnaam '{naam}' komt voor in de eigen definitie — "
                "gebruik de naam niet in de eigen definitie (wel eerder gedefinieerde begrippen)."
            )

        waarschuwingen.extend(check_vindplaatsen(b, bid, "Begrip", bron_ids))

        if "bron_verwijzing" in b and not (b.get("bron_verwijzing") or "").strip():
            waarschuwingen.append(
                f"[{bid or '?'}] Leeg 'bron_verwijzing' — laat het veld weg of vul een id in."
            )

        fouten.extend(_check_begrip_refs(
            b, bid, "Begrip", "verwijst_naar_begrippen", begrip_ids,
            [x for x in (b.get("verwijst_naar_begrippen") or []) if x],
        ))

        for rel in _object_items(b, "relaties", bid, "Begrip", fouten):
            rsoort = rel.get("soort", "")
            if rsoort and rsoort not in GELDIGE_RELATIE_SOORT:
                waarschuwingen.append(
                    f"[{bid or '?'}] Onbekende relatie-soort '{rsoort}' (verwacht: relatie, kenmerk)."
                )
            doel = rel.get("doel_begrip")
            if doel:
                fouten.extend(_check_begrip_refs(
                    b, bid, "Begrip", "relaties.doel_begrip", begrip_ids, [doel],
                ))

        # Koppeling met act 2 (alleen toetsbaar met --act2).
        for mid in (b.get("markering_ids") or []):
            if markering_index and mid not in markering_index:
                fouten.append(
                    f"[{bid or '?'}] markering_ids verwijst naar onbekende markering '{mid}'."
                )
            gedekte_markeringen.add(mid)

        # Herkomst t.o.v. de aangeleverde begrippenlijst (alleen met --begrippenlijst).
        herkomst = b.get("herkomst")
        if herkomst is not None and not isinstance(herkomst, dict):
            fouten.append(
                f"[{bid or '?'}] Begrip: 'herkomst' is geen object "
                "(verwacht: status/aangeleverd_id/motivatie)."
            )
            herkomst = None
        if begrippenlijst is not None:
            if not herkomst:
                waarschuwingen.append(
                    f"[{bid or '?'}] Geen 'herkomst' terwijl een begrippenlijst is "
                    "aangeleverd — registreer hergebruikt/aangepast/nieuw."
                )
        if herkomst:
            # Structuurfouten in de herkomst blokkeren: een onnavolgbare herkomst-registratie
            # maakt het hergebruik oncontroleerbaar. Alleen de ontbrekende motivatie blijft
            # een waarschuwing (inhoudelijk aandachtspunt, geen structuurfout).
            status = herkomst.get("status", "")
            if status not in GELDIGE_HERKOMST_STATUS:
                fouten.append(
                    f"[{bid or '?'}] Onbekende herkomst-status '{status}' "
                    "(verwacht: hergebruikt, aangepast, nieuw)."
                )
            elif status in ("hergebruikt", "aangepast"):
                aid = (herkomst.get("aangeleverd_id") or "").strip()
                if not aid:
                    fouten.append(
                        f"[{bid or '?'}] herkomst '{status}' zonder 'aangeleverd_id'."
                    )
                elif aangeleverde_ids and aid not in aangeleverde_ids:
                    fouten.append(
                        f"[{bid or '?'}] herkomst.aangeleverd_id '{aid}' staat niet in de "
                        "aangeleverde begrippenlijst."
                    )
                if status == "aangepast" and not (herkomst.get("motivatie") or "").strip():
                    waarschuwingen.append(
                        f"[{bid or '?'}] herkomst 'aangepast' zonder 'motivatie' — de "
                        "afwijking is een interpretatiekeuze die motivering vraagt."
                    )

    # Homoniem-signalering: dezelfde grondformulering onder meerdere begrippen is legitiem
    # (homoniemen splitsen), maar hoort een bewuste keuze te zijn — informeer de reviewer.
    grond_index: dict[str, list[str]] = {}
    for b in begrippen:
        grond = _norm_naam(b.get("grondformulering") or "")
        if grond:
            grond_index.setdefault(grond, []).append(b.get("id") or "?")
    for grond, ids in grond_index.items():
        if len(ids) > 1:
            waarschuwingen.append(
                f"Grondformulering '{grond}' levert meerdere begrippen op ({', '.join(ids)}) — "
                "controleer dat dit bewust gesplitste homoniemen zijn met onderscheidende namen."
            )

    for r in regels:
        rid = r.get("id", "")
        if not rid:
            fouten.append("Afleidingsregel heeft geen 'id' (verplicht voor feedback-koppeling).")
        else:
            if rid in geziene_ids:
                fouten.append(f"Id '{rid}' komt meerdere keren voor (begrip of afleidingsregel).")
            geziene_ids.add(rid)

        naam = (r.get("naam") or "").strip()
        if not naam:
            fouten.append(f"[{rid or '?'}] Afleidingsregel heeft geen 'naam'.")
        elif not _lijkt_werkwoordsvorm(naam):
            waarschuwingen.append(
                f"[{rid or '?'}] Regelnaam '{naam}' begint niet met een actieve "
                "werkwoordsvorm (bv. 'bepalen …', 'berekenen …', 'vaststellen …')."
            )

        regeltype = r.get("type", "")
        if not regeltype:
            fouten.append(
                f"[{rid or '?'}] Veld 'type' ontbreekt. "
                "Gebruik: beslisregel, rekenregel of specialisatieregel."
            )
        elif regeltype not in GELDIGE_REGELTYPEN:
            fouten.append(
                f"[{rid or '?'}] Ongeldig regeltype: '{regeltype}'. "
                "Gebruik: beslisregel, rekenregel of specialisatieregel."
            )

        # De regel gebruikt de begrippen als bouwstenen: uitvoer is verplicht en elk
        # gerefereerd begrip moet bestaan.
        uitvoer = r.get("uitvoer") or {}
        if not isinstance(uitvoer, dict):
            fouten.append(
                f"[{rid or '?'}] Afleidingsregel: 'uitvoer' is geen object "
                "(oud schema met vrije tekst? — verwacht: begrip_id/toelichting)."
            )
            uitvoer = {}
        uitvoer_id = (uitvoer.get("begrip_id") or "").strip()
        if not uitvoer_id:
            fouten.append(
                f"[{rid or '?'}] Afleidingsregel heeft geen 'uitvoer.begrip_id' — maak eerst "
                "een begrip voor wat de regel afleidt en verwijs daarnaar."
            )
        else:
            fouten.extend(_check_begrip_refs(
                r, rid, "Afleidingsregel", "uitvoer.begrip_id", begrip_ids, [uitvoer_id],
            ))

        # Elk invoer-/parameter-item verwijst per begrip_id naar zijn bouwsteen; een item
        # zónder begrip_id is een niet-geannoteerde bouwsteen en blokkeert (net als een
        # dangling verwijzing) — de regel is dan niet tegen de begrippen te valideren.
        invoer = _object_items(r, "invoer", rid, "Afleidingsregel", fouten)
        for i, item in enumerate(invoer, 1):
            if not (item.get("begrip_id") or "").strip():
                fouten.append(
                    f"[{rid or '?'}] Afleidingsregel: invoer-item {i} heeft geen 'begrip_id' — "
                    "maak eerst een begrip voor deze bouwsteen en verwijs daarnaar."
                )
        fouten.extend(_check_begrip_refs(
            r, rid, "Afleidingsregel", "invoer.begrip_id", begrip_ids,
            [(i.get("begrip_id") or "").strip() for i in invoer],
        ))

        parameters = _object_items(r, "parameters", rid, "Afleidingsregel", fouten)
        for i, item in enumerate(parameters, 1):
            if not (item.get("begrip_id") or "").strip():
                fouten.append(
                    f"[{rid or '?'}] Afleidingsregel: parameter-item {i} heeft geen 'begrip_id' — "
                    "maak eerst een begrip voor deze bouwsteen en verwijs daarnaar."
                )
        fouten.extend(_check_begrip_refs(
            r, rid, "Afleidingsregel", "parameters.begrip_id", begrip_ids,
            [(p.get("begrip_id") or "").strip() for p in parameters],
        ))

        if not invoer and not parameters:
            waarschuwingen.append(
                f"[{rid or '?'}] Afleidingsregel heeft geen 'invoer' en geen 'parameters' — "
                "waaruit wordt de uitvoer afgeleid?"
            )

        voorwaarden = _object_items(r, "voorwaarden", rid, "Afleidingsregel", fouten)
        for vw in voorwaarden:
            fouten.extend(_check_begrip_refs(
                r, rid, "Afleidingsregel", "voorwaarden.begrip_ids", begrip_ids,
                [x for x in (vw.get("begrip_ids") or []) if x],
            ))
            verbinding = vw.get("verbinding", "")
            if verbinding not in GELDIGE_VERBINDING:
                waarschuwingen.append(
                    f"[{rid or '?'}] Onbekende voorwaarde-verbinding '{verbinding}' "
                    "(verwacht: EN, OF of leeg)."
                )
        if regeltype == "beslisregel" and not voorwaarden:
            waarschuwingen.append(
                f"[{rid or '?'}] Beslisregel zonder 'voorwaarden' — waarop wordt beslist?"
            )

        waarschuwingen.extend(check_vindplaatsen(r, rid, "Afleidingsregel", bron_ids))

        for mid in (r.get("markering_ids") or []):
            if markering_index and mid not in markering_index:
                fouten.append(
                    f"[{rid or '?'}] markering_ids verwijst naar onbekende markering '{mid}'."
                )
            gedekte_markeringen.add(mid)

    # Dekkingscheck act 2 → act 3 (alleen met --act2): elke begrip-plichtige markering hoort
    # via markering_ids in een begrip te landen; elke Afleidingsregel-markering in een regel.
    if markering_index:
        for mid, klasse in markering_index.items():
            if mid in gedekte_markeringen:
                continue
            if klasse in BEGRIP_PLICHTIGE_KLASSEN:
                waarschuwingen.append(
                    f"Markering '{mid}' ({klasse}) landt in geen enkel begrip "
                    "(markering_ids) — dekking act 2 → act 3 onvolledig."
                )
            elif klasse == "Afleidingsregel":
                waarschuwingen.append(
                    f"Markering '{mid}' (Afleidingsregel) landt in geen enkele "
                    "afleidingsregel (markering_ids)."
                )

    return fouten, waarschuwingen


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Pre-check analyse.json voor review")
    parser.add_argument("--input", type=Path, required=True,
                        help="Pad naar analyse.json")
    parser.add_argument("--activiteit", choices=["2", "3"], required=True,
                        help="Activiteit 2 of 3")
    parser.add_argument("--act2", type=Path, default=None,
                        help="Pad naar de act-2 analyse.json (activeert de dekkingscheck "
                             "act 2 → act 3; alleen zinvol bij --activiteit 3)")
    parser.add_argument("--begrippenlijst", type=Path, default=None,
                        help="Pad naar de aangeleverde begrippenlijst.json (activeert de "
                             "herkomst-checks; alleen zinvol bij --activiteit 3)")
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

    if args.activiteit == "2":
        fouten, waarschuwingen = check_activiteit_2(data)
        context = f"{len(data.get('bronnen') or [])} bron(nen)"
    else:
        act2 = _lees_json(args.act2, "act-2-analyse") if args.act2 else None
        begrippenlijst = (
            _lees_json(args.begrippenlijst, "begrippenlijst") if args.begrippenlijst else None
        )
        fouten, waarschuwingen = check_activiteit_3(data, act2=act2, begrippenlijst=begrippenlijst)
        context = (data.get("werkgebied") or {}).get("naam", "?")

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
