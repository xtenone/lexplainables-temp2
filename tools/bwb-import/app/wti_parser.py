"""Parser voor de wetstechnische informatie (WTI) van een regeling.

De WTI (``wetstechnische-informatie``) levert verrijking die niet in de
toestand-XML zit: officiële citeertitel(s) en afkortingen, rechtsgebieden en
overheidsdomeinen (thesaurustermen) en de grondslag-relaties naar andere
regelingen. Alleen de voor de knowledge graph relevante velden worden gelezen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

logger = logging.getLogger(__name__)

# WTI-relatietag (kind van <regelingelement>) -> attribuut op WtiElementRel.
_REL_TAGS = {
    "grondslag-voor": "grondslag_voor",
    "wettelijke-bevoegdheid-voor": "bevoegdheid_voor",
    "verwijzing-door": "verwijzing_door",
}


@dataclass(slots=True)
class WtiElementRel:
    """Uitgaande relaties van één regelingelement (per ``label-id``): voor welke
    regelingen dit element grondslag/bevoegdheid is en welke ernaar verwijzen."""

    grondslag_voor: list[str] = field(default_factory=list)  # BWB-id's
    bevoegdheid_voor: list[str] = field(default_factory=list)
    verwijzing_door: list[str] = field(default_factory=list)


@dataclass(slots=True)
class WtiInfo:
    """Relevante WTI-velden voor verrijking van de wet-node."""

    citeertitels: list[str] = field(default_factory=list)
    afkortingen: list[str] = field(default_factory=list)
    niet_officiele_titels: list[str] = field(default_factory=list)
    eerstverantwoordelijke: str | None = None
    # (hoofdgebied, specifiekgebied|None) per rechtsgebied.
    rechtsgebieden: list[tuple[str, str | None]] = field(default_factory=list)
    overheidsdomeinen: list[str] = field(default_factory=list)
    grondslagen: list[str] = field(default_factory=list)  # BWB-id's
    # Verantwoordelijke organisatie (owms:kern/overheid:authority), bv. "Financiën".
    authority: str | None = None
    # Wetsfamilie: BWB-id's van verwante regelingen (ontdubbeld, zonder zichzelf).
    wetsfamilie: list[str] = field(default_factory=list)
    # Per regelingelement (label-id) de uitgaande relaties.
    element_relaties: dict[str, WtiElementRel] = field(default_factory=dict)


class WtiParser:
    """Zet een WTI-XML om naar :class:`WtiInfo` (defensief: velden optioneel)."""

    def parse(self, xml_path: Path) -> WtiInfo:
        root = etree.parse(str(xml_path)).getroot()
        algemeen = root.find("algemene-informatie")
        info = WtiInfo()
        if algemeen is not None:
            info.eerstverantwoordelijke = _tekst(algemeen.find("eerstverantwoordelijke"))
            info.afkortingen = _teksten(algemeen, "afkortingen/afkorting")
            info.niet_officiele_titels = _teksten(
                algemeen, "niet-officiele-titels/niet-officiele-titel"
            )
            info.citeertitels = _teksten(algemeen, "citeertitel") + _teksten(
                algemeen, "citeertitels/citeertitel"
            )
            for gebied in algemeen.iterfind("rechtsgebieden/rechtsgebied"):
                hoofd = _tekst(gebied.find("hoofdgebied"))
                if hoofd:
                    info.rechtsgebieden.append((hoofd, _tekst(gebied.find("specifiekgebied"))))
            info.overheidsdomeinen = _teksten(algemeen, "overheidsdomeinen/overheidsdomein")

        for grondslag in root.iterfind("gerelateerde-regelgeving/regeling/grondslagen/grondslag"):
            bwb_id = grondslag.get("bwb-id")
            if bwb_id and bwb_id not in info.grondslagen:
                info.grondslagen.append(bwb_id)

        # OWMS-kern: verantwoordelijke organisatie + eigen BWB-id (voor de
        # ontdubbeling van de wetsfamilie). Namespace-agnostisch (owms/overheid).
        authority = root.xpath("string(.//*[local-name()='kern']/*[local-name()='authority'])")
        info.authority = " ".join(authority.split()) or None
        zelf = root.xpath("string(.//*[local-name()='kern']/*[local-name()='identifier'])").strip()

        # Wetsfamilie: verwante regelingen (ontdubbeld, zonder de wet zelf).
        for gr in root.xpath(".//wetsfamilie/gerelateerde-regeling"):
            bwb_id = gr.get("bwb-id")
            if bwb_id and bwb_id != zelf and bwb_id not in info.wetsfamilie:
                info.wetsfamilie.append(bwb_id)

        # Per regelingelement (label-id) de uitgaande relaties.
        for element in root.xpath(".//regelingelement[@label-id]"):
            label_id = element.get("label-id")
            rel = info.element_relaties.setdefault(label_id, WtiElementRel())
            for tag, attr in _REL_TAGS.items():
                doelen = getattr(rel, attr)
                # grondslag-/bevoegdheid-voor dragen <gerelateerde-regeling>,
                # verwijzing-door <gerelateerd-regelingelement>; beide met @bwb-id.
                for gr in element.xpath(
                    f"{tag}/*[self::gerelateerde-regeling or self::gerelateerd-regelingelement]"
                ):
                    bwb_id = gr.get("bwb-id")
                    if bwb_id and bwb_id not in doelen:
                        doelen.append(bwb_id)
        # Regelingelementen zonder enige relatie dragen niets bij -> opschonen.
        info.element_relaties = {
            k: v
            for k, v in info.element_relaties.items()
            if v.grondslag_voor or v.bevoegdheid_voor or v.verwijzing_door
        }

        logger.info(
            "WTI geparst: %d citeertitels, %d rechtsgebieden, %d grondslagen, "
            "authority=%s, %d in wetsfamilie, %d elementen met relaties",
            len(info.citeertitels),
            len(info.rechtsgebieden),
            len(info.grondslagen),
            info.authority,
            len(info.wetsfamilie),
            len(info.element_relaties),
        )
        return info


def _tekst(element: etree._Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    return " ".join(element.text.split()) or None


def _teksten(element: etree._Element, pad: str) -> list[str]:
    resultaat: list[str] = []
    for node in element.iterfind(pad):
        tekst = _tekst(node)
        if tekst and tekst not in resultaat:
            resultaat.append(tekst)
    return resultaat
