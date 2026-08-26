"""Prompts voor de RegelSpraak-vervolgfase — gebouwd uit de regelspraak-skill-references (verbatim).

Net als engine/prompts.py voor de wetsanalyse: de analytische kennis blijft één gedeelde bron met
de skill (dezelfde `.claude/skills/regelspraak/references/*.md` op runtime). Twee stappen:
GegevensSpraak (objectmodel) en de RegelSpraak-regels, elk met een eigen schema + revise-variant.
"""

from __future__ import annotations

import hashlib
import json

from ..config import REGELSPRAAK_REFERENCES_DIR


def _hash(*teksten: str) -> str:
    h = hashlib.sha256()
    for t in teksten:
        h.update(t.encode("utf-8"))
    return h.hexdigest()[:16]


def _lees(naam: str) -> str:
    pad = REGELSPRAAK_REFERENCES_DIR / naam
    return pad.read_text(encoding="utf-8") if pad.exists() else ""


GEGEVENSSPRAAK_REF = _lees("gegevensspraak-referentie.md")
REGELS_REF = _lees("regels-en-resultaat-referentie.md")
EXPRESSIES_REF = _lees("expressies-en-operatoren-referentie.md")
VERTAALPATRONEN_REF = _lees("vertaalpatronen.md")
REGELSPRAAK_REFERENTIE_HASH = _hash(
    GEGEVENSSPRAAK_REF, REGELS_REF, EXPRESSIES_REF, VERTAALPATRONEN_REF
)

_SYSTEM = (
    "Je formaliseert geduide Nederlandse wet- en regelgeving naar een uitvoerbare specificatie in "
    "RegelSpraak v2.3.0 (de gecontroleerde natuurlijke taal van de Belastingdienst/ALEF), met "
    "daaronder GegevensSpraak (het objectmodel). Brongetrouwheid is niet-onderhandelbaar:\n"
    "- Gebruik UITSLUITEND echte RegelSpraak/GegevensSpraak-taalpatronen uit de meegegeven "
    "references. Verzin nooit syntax, sleutelwoorden, operatoren of predicaten. Wat er niet in "
    "staat, schrijf je niet — noteer het als validatiepunt.\n"
    "- Houd alles herleidbaar: elke declaratie en regel draagt een 'herkomst' naar het bron-begrip "
    "of de bron-afleidingsregel uit de wetsanalyse (begrip_ids/regel_id + vindplaatsen).\n"
    "- Citeer de termen uit de bron: de 'naam' is de voorkeursterm van het bijbehorende begrip; "
    "verzin geen nieuwe termen.\n"
    "- Markeer interpretatiekeuzes expliciet in 'twijfel'/'validatiepunten' i.p.v. schijnzekerheid.\n"
    "Geef UITSLUITEND geldig JSON terug, zonder uitleg of markdown-fences."
)

# De references als gelabelde secties. Ze verhuizen van de user-prompt naar het system-bericht:
# daar vormen ze per stap een byte-stabiele prefix die — met prompt caching aan — over rondes heen
# uit de cache wordt geserveerd i.p.v. elke call (incl. elke revisie) opnieuw vol betaald.
_REF_GEGEVENS = "REFERENTIE — GegevensSpraak-syntax:\n" + GEGEVENSSPRAAK_REF
_REF_REGELS = "REFERENTIE — RegelSpraak-regels en resultaatacties:\n" + REGELS_REF
_REF_EXPRESSIES = "REFERENTIE — expressies en operatoren:\n" + EXPRESSIES_REF
_REF_VERTAAL_GEGEVENS = "REFERENTIE — vertaalpatronen (JAS-klasse → GegevensSpraak):\n" + VERTAALPATRONEN_REF
_REF_VERTAAL_REGELS = "REFERENTIE — vertaalpatronen (afleidingsregel → resultaatactie):\n" + VERTAALPATRONEN_REF


def _system(*ref_secties: str) -> str:
    """Bouw het system-bericht: de vaste brongetrouwheids-instructie + de stap-references.
    Byte-stabiel binnen een stap → cachebaar (zie LiteLLMClient._system_message)."""
    return "\n\n".join((_SYSTEM, *ref_secties))


# --- schema's ----------------------------------------------------------------

_GEGEVENS_SCHEMA = {
    "eenheidssystemen": [{"naam": "<naam>", "regelspraak_tekst": "Eenheidssysteem ..."}],
    "domeinen": [
        {
            "naam": "<naam>",
            "regelspraak_tekst": "Domein ... is van het type ...",
            "herkomst": {"begrip_ids": ["b1"], "vindplaatsen": [{"bron_id": "br1", "lid": "<n>"}]},
        }
    ],
    "objecttypen": [
        {
            "id": "ot1",
            "naam": "<voorkeursterm uit het begrip>",
            "lidwoord": "de|het",
            "meervoud": "<meervoudsvorm>",
            "bezield": True,
            "attributen": [
                {"naam": "<naam>", "lidwoord": "de|het",
                 "datatype": "<Numeriek (...)|Tekst|Boolean|Datum-tijd|Percentage of een domeinnaam>",
                 "eenheid": "<optioneel>"}
            ],
            "kenmerken": [{"naam": "<naam>", "soort": "bijvoeglijk|bezittelijk|overig"}],
            "regelspraak_tekst": "Objecttype de ... (bezield)\n  ...",
            "herkomst": {"begrip_ids": ["b1"], "vindplaatsen": [{"bron_id": "br1", "lid": "<n>"}]},
            "twijfel": "<optioneel>",
        }
    ],
    "feittypen": [
        {
            "id": "ft1",
            "naam": "<naam>",
            "wederkerig": False,
            "rollen": [
                {"naam": "<rol>", "lidwoord": "de|het", "objecttype": "<objecttype-naam>",
                 "multipliciteit": "een|meerdere"}
            ],
            "relatiebeschrijving": "<optioneel>",
            "regelspraak_tekst": "Feittype ...",
            "herkomst": {"begrip_ids": ["b1"], "vindplaatsen": [{"bron_id": "br1", "lid": "<n>"}]},
        }
    ],
    "parameters": [
        {
            "id": "par1",
            "naam": "<naam>",
            "lidwoord": "de|het",
            "datatype": "<datatype of domeinnaam>",
            "eenheid": "<optioneel>",
            "regelspraak_tekst": "Parameter de ... : ...",
            "herkomst": {"regel_id": "r1", "vindplaatsen": [{"bron_id": "br1", "lid": "<n>"}]},
        }
    ],
    "dimensies": [],
    "tijdlijnen": [],
    "dagsoorten": [],
}

_REGELS_SCHEMA = {
    "regels": [
        {
            "id": "rs1",
            "naam": "<unieke, sprekende naam>",
            "soort": "gelijkstelling|kenmerktoekenning|consistentieregel|initialisatie|"
                     "objectcreatie|feitcreatie|verdeling|dagsoortdefinitie|startpuntbepaling",
            "regelspraak_tekst": "Regel ...\n  geldig altijd\n    ...",
            "herkomst": {"regel_id": "r1", "vindplaatsen": [{"bron_id": "br1", "lid": "<n>"}]},
            "twijfel": "<optioneel>",
        }
    ],
    "validatiepunten": ["<aandachtspunt voor multidisciplinaire validatie>"],
}


# --- context-blokken ---------------------------------------------------------

def _begrippen_blok(context: dict) -> str:
    return json.dumps(context.get("begrippen") or [], ensure_ascii=False, indent=2)


def _afleidingsregels_blok(context: dict) -> str:
    return json.dumps(context.get("afleidingsregels") or [], ensure_ascii=False, indent=2)


def _brondefinities_blok(context: dict) -> str:
    """Brondefinities + definitie-verwijzingen uit de bronnen (voeden domeinen/herleidbaarheid)."""
    uit: list[dict] = []
    for bron in context.get("bronnen") or []:
        for m in bron.get("brondefinities") or bron.get("markeringen") or []:
            if m.get("klasse") == "Brondefinitie":
                uit.append({"bron_id": bron.get("bron_id"), **m})
    return json.dumps(uit, ensure_ascii=False, indent=2)


# --- prompt-builders ---------------------------------------------------------

def gegevens_prompt(context: dict) -> tuple[str, str, dict, str]:
    """Stap 2 — bouw het objectmodel uit de begrippen (en afleidingsregels voor parameters)."""
    system = _system(_REF_GEGEVENS, _REF_VERTAAL_GEGEVENS)
    user = (
        "=== WERKGEBIED ===\n"
        + json.dumps(context.get("werkgebied") or {}, ensure_ascii=False, indent=2)
        + "\n\n=== BEGRIPPEN (wetsanalyse activiteit 3a — voeden de objecttypen/attributen/kenmerken) ===\n"
        + _begrippen_blok(context)
        + "\n\n=== AFLEIDINGSREGELS (voor de parameters: vaste waarden zoals tarieven/drempels) ===\n"
        + _afleidingsregels_blok(context)
        + "\n\n=== BRONDEFINITIES (voeden domeinen + herleidbaarheid) ===\n"
        + _brondefinities_blok(context)
        + "\n\nOPDRACHT (GegevensSpraak): bouw het objectmodel. Leid objecttypen af uit de "
        "rechtssubjecten/rechtsobjecten, attributen uit de variabelen, kenmerken uit "
        "booleaanse/ja-nee-eigenschappen, parameters uit de vaste waarden, feittypen uit de "
        "rechtsbetrekkingen (een begrip-'relatie' met een 'doel_begrip' is de kandidaat voor een "
        "feittype met rollen). Gebruik de begripsnaam als 'naam' (verzin geen termen). "
        "Dek ELK begrip-id dat door een afleidingsregel wordt gerefereerd (uitvoer/invoer/"
        "parameters/voorwaarden) met een declaratie — de regels-stap verwijst er op id naar. "
        "De regel-'parameters' dragen de gestructureerde waarde (waarde/eenheid/geldigheid): "
        "neem waarde + eenheid over in de parameterdeclaratie; een lege waarde (delegatie) → "
        "declareren zonder waarde + validatiepunt. Geef elk "
        "objecttype/feittype/parameter een stabiel id (ot1, ft1, par1, …) en een 'herkomst' naar "
        "het bron-begrip (begrip_ids) of de bron-regel (regel_id) + vindplaatsen. Schrijf de "
        "letterlijke GegevensSpraak in 'regelspraak_tekst'. Verzin geen gegevens die niet uit de "
        "bron volgen; markeer twijfel."
    )
    return system, user, _GEGEVENS_SCHEMA, _hash(system, user)


def regels_prompt(context: dict) -> tuple[str, str, dict, str]:
    """Stap 3 — schrijf de RegelSpraak-regels uit de afleidingsregels, bovenop het objectmodel."""
    system = _system(_REF_REGELS, _REF_EXPRESSIES, _REF_VERTAAL_REGELS)
    user = (
        "=== GEGEVENSSPRAAK (het objectmodel — verwijs ALLEEN naar hierin gedeclareerde "
        "objecttypen/attributen/kenmerken/parameters/rollen) ===\n"
        + json.dumps(context.get("gegevensspraak") or {}, ensure_ascii=False, indent=2)
        + "\n\n=== AFLEIDINGSREGELS (wetsanalyse activiteit 3b — voeden de regels) ===\n"
        + _afleidingsregels_blok(context)
        + "\n\nOPDRACHT (RegelSpraak-regels): maak per afleidingsregel een Regel. De regelvelden "
        "zijn op BEGRIP-ID's gebouwd — volg 'uitvoer.begrip_id' naar de declaratie met dat id in "
        "haar herkomst.begrip_ids (dat is het attribuut/kenmerk in het resultaatdeel); idem voor "
        "'invoer' en 'parameters' (de operanden). Match nooit op naam-strings. Kies de juiste "
        "resultaatactie (rekenregel → Gelijkstelling-berekening; beslis-/specialisatieregel → "
        "Kenmerktoekenning of Consistentieregel). Bouw het voorwaardendeel uit 'voorwaarden': "
        "één conditie → enkelvoudig 'indien …'; meerdere → een samengestelde voorwaarde waarbij "
        "'verbinding' de kwantor bepaalt (EN → 'aan alle volgende voorwaarden', OF → 'aan ten "
        "minste één van de volgende voorwaarden'). Een parameter-'geldigheid' → een "
        "'geldig'-regelversie. Gebruik uitsluitend de echte RegelSpraak-operatoren/predicaten. "
        "Geef elke regel een stabiel id (rs1, …), een 'geldig'-regelversie, de letterlijke "
        "'regelspraak_tekst', en een 'herkomst' (regel_id + vindplaatsen). Markeer "
        "interpretatiekeuzes in 'twijfel' en noteer aandachtspunten als validatiepunten."
    )
    return system, user, _REGELS_SCHEMA, _hash(system, user)


def revise_prompt(stap: str, vorige: dict, feedback: dict) -> tuple[str, str, dict, str]:
    """Herzie GegevensSpraak (stap='rs-gegevens') of de regels (stap='rs-regels') op feedback."""
    if stap == "rs-gegevens":
        schema = _GEGEVENS_SCHEMA
        system = _system(_REF_GEGEVENS, _REF_VERTAAL_GEGEVENS)
        vorig_blok = json.dumps(vorige.get("gegevensspraak") or {}, ensure_ascii=False, indent=2)
        extra = (
            "\n\nOPDRACHT: lever de HERZIENE GegevensSpraak (objecttypen/attributen/kenmerken/"
            "domeinen/parameters/feittypen). Verwerk elke per-item-correctie (per id) en de "
            "algemene feedback. HOUD ID'S STABIEL. Behoud 'herkomst' en 'regelspraak_tekst'."
        )
    else:
        schema = _REGELS_SCHEMA
        system = _system(_REF_REGELS, _REF_EXPRESSIES)
        vorig_blok = json.dumps(
            {"regels": vorige.get("regels") or [], "validatiepunten": vorige.get("validatiepunten") or []},
            ensure_ascii=False, indent=2,
        )
        extra = (
            "\n\nOPDRACHT: lever de HERZIENE RegelSpraak-regels. Verwerk elke per-item-correctie "
            "(per id) en de algemene feedback. HOUD ID'S STABIEL. Verwijs alleen naar gedeclareerde "
            "gegevens; gebruik uitsluitend echte RegelSpraak-taalpatronen."
        )
    user = (
        "=== JE VORIGE VERSIE ===\n" + vorig_blok
        + "\n\n=== FEEDBACK VAN DE ANALIST (verwerk ELK punt) ===\n"
        + json.dumps(feedback, ensure_ascii=False, indent=2)
        + extra
    )
    return system, user, schema, _hash(system, user)
