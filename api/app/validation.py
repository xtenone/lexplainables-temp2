"""Validatie — hergebruikt de skill-checks en voegt de harde brongetrouwheid-invariant toe.

Twee soorten:
  - SCHEMA (check_activiteit_2/3 uit validate_analyse.py): FOUTEN blokkeren — de orchestrator
    probeert eerst auto-correctie en zet de job anders naar `fout`, ook in review:false
    (gelijke handhaving met het skill-spoor, waar exit 2 de review-server tegenhoudt).
    WAARSCHUWINGEN blokkeren niet; die gaan als context mee naar het checkpoint.
  - HARD (brongetrouwheid): geldt ALTIJD, ook in review:false. Faalt dit na auto-correctie,
    dan gaat de job naar `fout` — nooit stil naar `klaar`.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import unicodedata
from pathlib import Path

from .config import REGELSPRAAK_SCRIPTS, SKILL_SCRIPTS


def _load_module_from(scripts_dir, naam: str):
    """Laad een skill-script als module (de scripts vormen geen package)."""
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    pad = scripts_dir / f"{naam}.py"
    spec = importlib.util.spec_from_file_location(naam, pad)
    if spec is None or spec.loader is None:
        raise ImportError(f"Kan skill-script niet laden: {pad}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_skill_module(naam: str):
    return _load_module_from(SKILL_SCRIPTS, naam)


_validate = _load_skill_module("validate_analyse")
GELDIGE_JAS_KLASSEN: set[str] = _validate.GELDIGE_JAS_KLASSEN  # canonieke bron (drift-fix)
JAS_KLASSEN_VOLGORDE: tuple[str, ...] = _validate.JAS_KLASSEN_VOLGORDE  # weergave-volgorde (wa-table.png)
jas_sorteersleutel = _validate.jas_sorteersleutel
GELDIGE_REGELTYPEN: set[str] = _validate.GELDIGE_REGELTYPEN
BEGRIP_PLICHTIGE_KLASSEN: set[str] = _validate.BEGRIP_PLICHTIGE_KLASSEN

# RegelSpraak-pre-check (gedeeld met de skill): dezelfde mechanische controles als
# validate_regelspraak.py — geen drift tussen het skill- en het dienst-spoor.
_validate_rs = _load_module_from(REGELSPRAAK_SCRIPTS, "validate_regelspraak")
GELDIGE_REGELSOORTEN: set[str] = _validate_rs.GELDIGE_REGELSOORTEN


# Concerns die in de API door de harde, genormaliseerde brongetrouwheid_check worden gedekt.
# De skill-checks rapporteren ze óók (rauwe substring-match, zonder normalisatie — de
# citaat-mismatch daar is sinds de hardening een blokkerende FOUT), wat tot dubbele en soms
# vals-positieve meldingen leidt. We filteren ze hier — uit fouten én waarschuwingen — zodat per
# concern precies één (de harde, genormaliseerde) melding overblijft. De skill-scripts zelf
# blijven ongemoeid: in het skill-spoor is die check de enige citaat/vindplaats-controle.
_OVERLAPT_MET_HARD = (
    "lijkt geen letterlijk citaat",        # citaat (act 2)
    "Veld 'vindplaats' ontbreekt",         # vindplaats (act 2: markering, lid-relatief)
    "geen 'vindplaatsen'",                 # vindplaatsen (act 3: begrip/afleidingsregel)
)


def schema_check(
    data: dict,
    activiteit: str,
    *,
    act2: dict | None = None,
    begrippenlijst: dict | None = None,
) -> tuple[list[str], list[str]]:
    """Zachte schema/volledigheidscheck — delegeert naar de skill-functies.

    Waarschuwingen die de harde brongetrouwheid_check al dekt (citaat, vindplaats) worden
    uitgefilterd om dubbele meldingen in de review te voorkomen.

    Voor activiteit 3 activeren `act2` (de goedgekeurde act-2-analyse) de dekkings- en
    markering-id-checks en `begrippenlijst` (de aangeleverde lijst) de herkomst-checks —
    zelfde patroon als `regelspraak_schema_check` met `ingest`.
    """
    if activiteit == "2":
        fouten, waarschuwingen = _validate.check_activiteit_2(data)
    else:
        fouten, waarschuwingen = _validate.check_activiteit_3(
            data, act2=act2, begrippenlijst=begrippenlijst
        )
    fouten = [f for f in fouten if not any(m in f for m in _OVERLAPT_MET_HARD)]
    waarschuwingen = [
        w for w in waarschuwingen if not any(m in w for m in _OVERLAPT_MET_HARD)
    ]
    return fouten, waarschuwingen


def _rs_stap_naar_skill(stap: str) -> str:
    """De API-stapnamen (rs-gegevens/rs-regels) → de skill-CLI-namen waarop check_ingest brancht."""
    return "gegevensspraak" if stap == "rs-gegevens" else "regels"


def regelspraak_schema_check(
    data: dict, stap: str, ingest: dict | None = None
) -> tuple[list[str], list[str]]:
    """Zachte pre-check voor de RegelSpraak-fase — delegeert naar de skill-functies.

    stap ∈ {'rs-gegevens', 'rs-regels'}. Net als bij act-2/3 blokkeren fouten hier niet hard;
    ze gaan als waarschuwing mee naar het checkpoint (review:true) of worden gelogd (review:false).
    De harde invariant (herkomst aanwezig + geldig) zit in regelspraak_brongetrouwheid_check.

    Is `ingest` meegegeven (de wetsanalyse als startbasis, zie orchestrator._rs_gegevens_context),
    dan komt daar de **dekkingscheck** bij: een ingest-begrip/-afleidingsregel dat door geen enkele
    declaratie/regel wordt geraakt → waarschuwing (gedekt, of bewust buiten scope).
    """
    if stap == "rs-gegevens":
        fouten, waarschuwingen = _validate_rs.check_gegevensspraak(data)
    else:
        fouten, waarschuwingen = _validate_rs.check_regels(data)
    if ingest:
        _, dekking = _validate_rs.check_ingest(data, _rs_stap_naar_skill(stap), ingest)
        waarschuwingen = waarschuwingen + dekking
    return fouten, waarschuwingen


def regelspraak_brongetrouwheid_check(
    data: dict, stap: str, ingest: dict | None = None
) -> list[str]:
    """Harde controle die altijd geldt: elke declaratie/regel draagt een herkomst naar de
    wetsanalyse (begrip/regel + vindplaats). Zonder herkomst is de formalisering niet herleidbaar
    naar de wet → schending (job → fout, ook in review:false).

    Is `ingest` meegegeven, dan toetst de check óók de **integriteit** van die herkomst: een
    `begrip_id`/`regel_id`/`bron_id` dat niet in de wetsanalyse bestaat (dangling) is net zo'n
    harde schending — anders is de herleidbaarheid alleen schijn.
    """
    schendingen: list[str] = []
    if stap == "rs-gegevens":
        gs = data.get("gegevensspraak") or {}
        items = [
            (o.get("id") or o.get("naam") or "?", o)
            for groep in ("objecttypen", "feittypen", "parameters", "domeinen")
            for o in (gs.get(groep) or [])
        ]
    else:
        items = [(r.get("id") or r.get("naam") or "?", r) for r in (data.get("regels") or [])]
    for iid, item in items:
        if not _validate_rs.heeft_herkomst(item):
            schendingen.append(f"[{iid}] Herkomst ontbreekt (herleidbaarheid naar de wet verplicht).")
    if ingest:
        dangling, _ = _validate_rs.check_ingest(data, _rs_stap_naar_skill(stap), ingest)
        schendingen.extend(dangling)
    return schendingen


# --- harde brongetrouwheid-invariant -----------------------------------------

_WS = re.compile(r"\s+")
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "«": '"', "»": '"'})
# De MCP levert de lid-tekst met intref/extref als inline-Markdown-link ([label](jci-target));
# de frontend rendert daaruit de klikbare verwijzing. Een markering citeert echter het zichtbare
# label, niet de link-syntax — dus vóór de citaat-vergelijking vervangen we [label](target) door
# het label. (Alleen bij vergelijken: de opgeslagen lid-tekst houdt de markup voor de UI.)
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")


def _strip_md_links(tekst: str) -> str:
    """Vervang inline-Markdown-links [label](target) door hun zichtbare label."""
    return _MD_LINK.sub(r"\1", tekst)


def normaliseer(tekst: str) -> str:
    """Normaliseer unicode-compositie (NFC) + whitespace + typografische quotes, zodat echte
    citaten niet vals-positief zijn. NFC voorkomt dat een composé 'é' (U+00E9) en een
    decomposé 'e'+combining-accent (U+0065 U+0301) — visueel identiek — als ongelijk gelden."""
    return _WS.sub(" ", unicodedata.normalize("NFC", tekst).translate(_QUOTES)).strip().lower()


def brongetrouwheid_check(data: dict, activiteit: str) -> list[str]:
    """Harde controles die altijd gelden, werkgebied-breed. Geeft een lijst schendingen terug
    (leeg = ok). Activiteit 2 controleert per bron: bronreferentie aanwezig, en elke markering
    een vindplaats + letterlijk citaat uit de leden-tekst van DIE bron. Activiteit 3 controleert
    dat elk begrip/regel ten minste één vindplaats heeft."""
    schendingen: list[str] = []

    if activiteit == "2":
        bronnen = data.get("bronnen") or []
        for bron in bronnen:
            label = bron.get("label") or bron.get("bron_id") or "?"
            if not (bron.get("bronreferentie") or "").strip():
                schendingen.append(
                    f"[{label}] Bronreferentie (jci) ontbreekt — moet uit de MCP komen, niet uit het LLM."
                )
            leden_genorm = normaliseer(
                _strip_md_links(" ".join((lid.get("tekst") or "") for lid in (bron.get("leden") or [])))
            )
            for m in bron.get("markeringen") or []:
                mid = m.get("id", "?")
                if not (m.get("vindplaats") or "").strip():
                    schendingen.append(f"[{mid}] Vindplaats ontbreekt (herleidbaarheid verplicht).")
                formulering = (m.get("formulering") or "").strip()
                # Hergebruik de canonieke citaat-toets uit het skill-script (drift-fix): die
                # respecteert beletselteken ('...'/'…') en vierkante-haak-invoegingen ([...]).
                if (
                    formulering
                    and leden_genorm
                    and not _validate.fragmenten_letterlijk(normaliseer(formulering), leden_genorm)
                ):
                    kort = formulering[:60] + ("…" if len(formulering) > 60 else "")
                    schendingen.append(
                        f"[{mid}] Formulering is geen letterlijk citaat uit de leden-tekst: '{kort}'"
                    )
    else:
        for item in (data.get("begrippen") or []) + (data.get("afleidingsregels") or []):
            iid = item.get("id", "?")
            if not (item.get("vindplaatsen") or []):
                schendingen.append(f"[{iid}] Vindplaatsen ontbreken (herleidbaarheid verplicht).")

    return schendingen
