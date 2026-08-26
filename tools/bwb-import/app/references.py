"""Herkenning van verwijzingen tussen wetsartikelen.

Primair worden de gestructureerde ``<intref>``/``<extref>``-elementen uit de
toestand-XML gebruikt (met ``bwb-id``, ``doc`` en ``bwb-ng-variabel-deel``).
Als fallback detecteert een regex losse tekstverwijzingen zoals ``artikel 4``,
``artikel 6:162 BW`` of ``artikel 3:2 Awb`` die niet getagd zijn.
"""

from __future__ import annotations

import re

from lxml import etree

from app.afkortingen import zoek_bwb_id
from app.models import Verwijzing, VerwijzingSoort

# Verwijzingen mogen niet uit meta-data-subtrees komen.
_REF_XPATH = ".//*[self::intref or self::extref][not(ancestor::meta-data)]"

# Losse tekstverwijzingen: "artikel 4", "12a", "10.1", "3:2 Awb", "6:162 BW".
# Vangt het artikelnummer (cijfers met optionele letter/punt/dubbelepunt) plus
# een optionele wetafkorting (hoofdletter-initiaal, bv. BW, Awb, Sr).
# Geen IGNORECASE: de wetafkorting (bv. BW, Awb, Sr) begint met een hoofdletter,
# zodat losse woorden als "en"/"van" niet als afkorting worden aangezien.
_TEXT_REF = re.compile(
    r"\b[Aa]rtikel(?:en)?\s+"
    r"(?P<nummer>\d+[a-z]?(?:[.:]\d+[a-z]?)*)"
    r"(?:\s+(?P<wet>[A-Z][A-Za-z]{0,6}))?"
)

# Onderdelen van een jci-verwijzing (bv. "jci1.3:c:BWBR0005537&artikel=3:40").
_JCI_BWB = re.compile(r":c:(BWBR\d+)")
_JCI_ARTIKEL = re.compile(r"[&?]artikel=([^&]+)")
_JCI_LID = re.compile(r"[&?]lid=([^&]+)")
_JCI_ONDERDEEL = re.compile(r"[&?]o=([^&]+)")
_JCI_STRUCTUUR = re.compile(r"[&?](hoofdstuk|titeldeel|afdeling|paragraaf)=([^&]+)")


def jci_doel(doc: str | None) -> tuple[str | None, str | None, str | None]:
    """Ontleed een jci-``doc`` tot ``(bwb_id, artikelnummer, lidnummer)``.

    Versieparameters (``&z=``/``&g=``) worden genegeerd. Elk veld is ``None``
    als het niet in de verwijzing voorkomt (bv. een verwijzing naar een heel
    hoofdstuk levert geen artikel/lid).
    """
    if not doc:
        return (None, None, None)
    bwb = _JCI_BWB.search(doc)
    # Geneste circulaire-divisies dragen het volledige pad als herhaalde
    # ``&artikel=``-segmenten (bv. ``&artikel=79&artikel=79.5a``); het laatste is
    # het meest specifieke doel. Voor gewone wetten is er precies één segment.
    artikelen = _JCI_ARTIKEL.findall(doc)
    lidnrs = _JCI_LID.findall(doc)
    return (
        bwb.group(1) if bwb else None,
        artikelen[-1] if artikelen else None,
        lidnrs[-1] if lidnrs else None,
    )


def jci_to_ref_key(doc: str | None) -> str | None:
    """Vorm een stabiele artikelsleutel ``{bwb}#artikel={nr}`` uit een jci-doc.

    Versieparameters (``&z=``/``&g=``) worden genegeerd. Geeft ``None`` als de
    verwijzing geen concreet artikel aanduidt (bv. naar een heel hoofdstuk),
    zodat er geen onterechte VERWIJST_NAAR ontstaat.
    """
    bwb, artikel, _ = jci_doel(doc)
    if not bwb or not artikel:
        return None
    return f"{bwb}#artikel={artikel}"


def jci_doel_ref_key(doc: str | None) -> tuple[str | None, str | None]:
    """Ontleed een jci-doc tot ``(ref_key, doel_soort)`` op élk niveau.

    Anders dan :func:`jci_to_ref_key` (alleen artikel-niveau) resolveert deze
    ook hele-structuur-, lid- en onderdeel-doelen:

    - ``&artikel=…``                     -> ``{bwb}#artikel={nr}`` ("artikel")
    - ``… &lid=…``                       -> ``…#lid={l}`` ("lid")
    - ``… &o=…[&o=…]``                   -> ``…#o={o1}[#o={o2}]`` ("onderdeel")
    - alleen ``&hoofdstuk=``/…           -> ``{bwb}#hoofdstuk={nr}`` (soortnaam)
    - alleen ``:c:BWBR…``                -> ``{bwb}`` ("wet")

    Versieparameters (``&z=``/``&g=``) worden genegeerd; van herhaalde
    ``&artikel=``-/structuursegmenten telt het laatste (meest specifieke).
    """
    if not doc:
        return (None, None)
    bwb_match = _JCI_BWB.search(doc)
    if not bwb_match:
        return (None, None)
    bwb = bwb_match.group(1)

    artikelen = _JCI_ARTIKEL.findall(doc)
    if artikelen:
        ref_key, soort = f"{bwb}#artikel={artikelen[-1]}", "artikel"
        lidnrs = _JCI_LID.findall(doc)
        if lidnrs:
            ref_key, soort = f"{ref_key}#lid={lidnrs[-1]}", "lid"
        onderdelen = _JCI_ONDERDEEL.findall(doc)
        if onderdelen:
            # Geneste onderdelen dragen het pad als herhaalde &o=-segmenten.
            ref_key = ref_key + "".join(f"#o={o}" for o in onderdelen)
            soort = "onderdeel"
        return (ref_key, soort)

    structuren = _JCI_STRUCTUUR.findall(doc)
    if structuren:
        naam, waarde = structuren[-1]
        return (f"{bwb}#{naam}={waarde}", naam)

    return (bwb, "wet")


def _normaliseer(tekst: str | None) -> str:
    return re.sub(r"\s+", " ", tekst or "").strip()


def extract_references(element: etree._Element, *, eigen_bwb_id: str) -> list[Verwijzing]:
    """Haal gestructureerde verwijzingen uit een element (artikel of lid).

    De ``soort`` wordt bepaald door het tag-type (``intref``/``extref``); een
    ``extref`` naar de eigen wet wordt alsnog als intern beschouwd.
    """
    verwijzingen: list[Verwijzing] = []
    for ref in element.xpath(_REF_XPATH):
        doel_bwb = ref.get("bwb-id")
        is_intern = ref.tag == "intref" or (doel_bwb == eigen_bwb_id)
        verwijzingen.append(
            Verwijzing(
                soort=VerwijzingSoort.INTERN if is_intern else VerwijzingSoort.EXTERN,
                tekst=_normaliseer("".join(ref.itertext())),
                doel_bwb_id=doel_bwb,
                doel_pad=ref.get("bwb-ng-variabel-deel"),
                doc=ref.get("doc"),
                verwijzing_id=ref.get("verwijzing-id"),
            )
        )
    return verwijzingen


def detect_textual_references(tekst: str, *, eigen_bwb_id: str) -> list[Verwijzing]:
    """Detecteer losse (ongetagde) tekstverwijzingen naar artikelen (fallback).

    Een herkende wetafkorting wordt via :mod:`app.afkortingen` naar een BWB-id
    vertaald; zonder afkorting geldt de verwijzing als intern (eigen wet).
    Matches met een onbekende afkorting worden overgeslagen (te onzeker).
    """
    treffers: list[Verwijzing] = []
    for match in _TEXT_REF.finditer(tekst):
        nummer = match.group("nummer")
        wet = match.group("wet")
        if wet:
            doel_bwb = zoek_bwb_id(wet, nummer)
            if doel_bwb is None:
                continue
            anker = f"artikel {nummer} {wet}"
        else:
            doel_bwb = eigen_bwb_id
            anker = f"artikel {nummer}"
        treffers.append(
            Verwijzing(
                soort=VerwijzingSoort.TEKSTUEEL,
                tekst=anker,
                doel_bwb_id=doel_bwb,
                doel_artikel=nummer,
            )
        )
    return treffers
