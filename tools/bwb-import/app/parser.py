"""Parser voor de BWB toestand-XML (lxml), met optionele XSD-validatie.

Gebouwd op de geverifieerde structuur:
``toestand -> wetgeving -> wet-besluit -> wettekst ->
hoofdstuk/afdeling/paragraaf -> artikel -> lid -> al``.

De structurele opbouw verloopt via een generieke recursie zodat wisselende
nesting (afdeling in hoofdstuk, paragraaf in afdeling, ...) en latere
uitbreiding naar andere regelingsoorten werken zonder modelwijziging.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from lxml import etree

from app.models import (
    Artikel,
    Bijlage,
    Divisie,
    Illustratie,
    Lid,
    Onderdeel,
    Ondertekenaar,
    Structuurdeel,
    Verwijzing,
    Wet,
)
from app.references import extract_references

logger = logging.getLogger(__name__)

# Tags die als structuurdeel worden behandeld (label = structuur-soort).
_STRUCTUUR_TAGS = {
    "hoofdstuk": "hoofdstuk",
    "titeldeel": "titeldeel",
    "afdeling": "afdeling",
    "paragraaf": "paragraaf",
}


class ParseError(RuntimeError):
    """De XML kon niet als geldige toestand worden geïnterpreteerd."""


class ToestandParser:
    """Zet een toestand-XML om naar het :class:`~app.models.Wet`-model."""

    def __init__(self, schema_path: Path | None = None) -> None:
        self._schema_path = schema_path
        self._schema: etree.XMLSchema | None = None

    # ------------------------------------------------------------- validatie
    def validate(self, xml_path: Path) -> bool:
        """Valideer tegen het XSD. Niet-blokkerend: faalt zacht met waarschuwing.

        Geeft ``True`` bij geldig, ``False`` bij ongeldig of als het schema niet
        beschikbaar is.
        """
        if self._schema_path is None:
            logger.warning("Geen XSD opgegeven; validatie overgeslagen")
            return False
        try:
            schema = self._load_schema()
            doc = etree.parse(str(xml_path))
            schema.assertValid(doc)
            logger.info("XSD-validatie geslaagd voor %s", xml_path.name)
            return True
        except etree.DocumentInvalid as exc:
            logger.warning("XSD-validatie mislukt voor %s: %s", xml_path.name, exc)
            return False
        except (etree.XMLSchemaParseError, OSError) as exc:
            logger.warning("XSD kon niet worden geladen (%s); validatie overgeslagen", exc)
            return False

    def _load_schema(self) -> etree.XMLSchema:
        if self._schema is None:
            assert self._schema_path is not None
            self._schema = etree.XMLSchema(etree.parse(str(self._schema_path)))
        return self._schema

    # ----------------------------------------------------------------- parse
    def parse(self, xml_path: Path) -> Wet:
        """Parse de toestand-XML naar een :class:`Wet`."""
        tree = etree.parse(str(xml_path))
        root = tree.getroot()
        if root.tag != "toestand":
            raise ParseError(f"Onverwacht root-element: {root.tag!r} (verwacht 'toestand')")

        bwb_id = root.get("bwb-id") or ""
        wetgeving = root.find("wetgeving")
        if wetgeving is None:
            raise ParseError("Geen <wetgeving>-element gevonden")

        wet = Wet(
            bwb_id=bwb_id,
            citeertitel=self._tekst(wetgeving.find("citeertitel")),
            opschrift=self._tekst(wetgeving.find("intitule")),
            soort=wetgeving.get("soort", ""),
            geldig_vanaf=root.get("inwerkingtreding"),
            geldig_tot=None,
            label_id=wetgeving.get("label-id"),
            vast_deel_url=root.get("bwb-ng-vast-deel"),
            **self._wet_aanhef(wetgeving),
            **self._wet_brondata(wetgeving),
        )

        # Ministeriële regelingen dragen dezelfde bouwstenen als een
        # wettekst, maar onder <regeling>/<regeling-tekst>.
        wettekst = wetgeving.find("wet-besluit/wettekst")
        if wettekst is None:
            wettekst = wetgeving.find("regeling/regeling-tekst")
        if wettekst is not None:
            for child in wettekst:
                tag = child.tag if isinstance(child.tag, str) else ""
                if tag in _STRUCTUUR_TAGS:
                    wet.structuurdelen.append(self._parse_structuurdeel(child, bwb_id))
                elif tag == "artikel":
                    wet.losse_artikelen.append(self._parse_artikel(child, bwb_id))
            # Bijlagen staan náást de wettekst: kind van <wet-besluit>/<regeling>.
            houder = wettekst.getparent()
            if houder is not None:
                for bijlage in houder.iterfind("bijlage"):
                    wet.bijlagen.append(self._parse_bijlage(bijlage, bwb_id))
        else:
            # Circulaires/beleidsregels dragen geen wettekst maar een
            # recursieve <circulaire.divisie>-boom.
            circulaire = wetgeving.find("circulaire/circulaire-tekst")
            if circulaire is not None:
                for child in circulaire.iterfind("circulaire.divisie"):
                    wet.divisies.append(self._parse_divisie(child, bwb_id))
            else:
                logger.warning(
                    "Geen <wettekst>, <regeling-tekst> of <circulaire> gevonden voor %s",
                    bwb_id,
                )
                return wet

        wet.ondertekenaars = self._parse_ondertekenaars(wetgeving)

        logger.info(
            "Parse klaar voor %s: %d structuurdelen, %d losse artikelen, %d divisies, "
            "%d bijlagen, %d ondertekenaars",
            bwb_id,
            len(wet.structuurdelen),
            len(wet.losse_artikelen),
            len(wet.divisies),
            len(wet.bijlagen),
            len(wet.ondertekenaars),
        )
        return wet

    # ------------------------------------------------------------- structuur
    def _parse_structuurdeel(self, element: etree._Element, bwb_id: str) -> Structuurdeel:
        kop = element.find("kop")
        deel = Structuurdeel(
            id=self._knoop_id(bwb_id, element),
            soort=_STRUCTUUR_TAGS[element.tag],
            nummer=self._tekst(kop.find("nr")) if kop is not None else "",
            label=self._tekst(kop.find("label")) if kop is not None else "",
            titel=self._tekst(kop.find("titel")) if kop is not None else "",
            jci=self._element_jci(element),
            label_id=element.get("label-id"),
        )
        for child in element:
            tag = child.tag if isinstance(child.tag, str) else ""
            if tag in _STRUCTUUR_TAGS:
                deel.subdelen.append(self._parse_structuurdeel(child, bwb_id))
            elif tag == "artikel":
                deel.artikelen.append(self._parse_artikel(child, bwb_id))
        return deel

    def _parse_divisie(self, element: etree._Element, bwb_id: str) -> Divisie:
        """Parse een ``<circulaire.divisie>`` (recursief) uit een circulaire.

        De divisie draagt een eigen tekst (``./tekst``) én kan subdivisies
        bevatten; onderdelen (``<lijst>/<li>``) en verwijzingen komen uit die
        ``./tekst``. Verwijzingen binnen onderdelen worden op divisie-niveau
        uitgesloten (die horen bij het onderdeel-node) om dubbeling te vermijden.
        """
        kop = element.find("kop")
        tekst_el = element.find("tekst")
        divisie = Divisie(
            id=self._knoop_id(bwb_id, element),
            nummer=self._tekst(kop.find("nr")) if kop is not None else "",
            label=element.get("label", ""),
            titel=self._tekst(kop.find("titel")) if kop is not None else "",
            tekst=self._divisie_tekst(element),
            jci=self._element_jci(element),
            inwerking=element.get("inwerking"),
            bron=element.get("bron"),
            effect=element.get("effect"),
            status=element.get("status"),
            terugwerkend_tot=self._terugwerkend(element),
            wijzigingsbronnen=self._wijzigingsbronnen(element),
            verwijzingen=self._verwijzingen_scope(
                element, bwb_id, base="./tekst//*", extra_excl=" and not(ancestor::li)"
            ),
            onderdelen=self._parse_onderdelen(tekst_el, bwb_id) if tekst_el is not None else [],
            voetnoten=[
                self._noot_tekst(noot) for noot in element.xpath("./tekst//noot[not(ancestor::li)]")
            ],
            illustraties=self._illustraties(
                element, base="./tekst//illustratie", extra_excl=" and not(ancestor::li)"
            ),
        )
        for sub in element.iterfind("circulaire.divisie"):
            divisie.subdivisies.append(self._parse_divisie(sub, bwb_id))
        return divisie

    def _parse_bijlage(self, element: etree._Element, bwb_id: str) -> Bijlage:
        """Parse een ``<bijlage>`` (kind van ``<wet-besluit>``/``<regeling>``).

        Een bijlage is container én tekstdrager: eigen alinea's + onderdelen, en
        kan eigen artikelen bevatten (die als aparte ``Artikel``-nodes tellen).
        Tekst/verwijzingen/onderdelen op bijlage-niveau sluiten de inhoud van
        geneste artikelen/leden/onderdelen uit om dubbeling te vermijden.
        """
        kop = element.find("kop")
        excl = " and not(ancestor::artikel) and not(ancestor::lid) and not(ancestor::li)"
        bijlage = Bijlage(
            id=self._knoop_id(bwb_id, element),
            nummer=self._tekst(kop.find("nr")) if kop is not None else "",
            label=self._tekst(kop.find("label")) if kop is not None else element.get("label", ""),
            titel=self._tekst(kop.find("titel")) if kop is not None else "",
            tekst=self._bijlage_tekst(element),
            jci=self._element_jci(element),
            inwerking=element.get("inwerking"),
            bron=element.get("bron"),
            effect=element.get("effect"),
            status=element.get("status"),
            terugwerkend_tot=self._terugwerkend(element),
            wijzigingsbronnen=self._wijzigingsbronnen(element),
            verwijzingen=self._verwijzingen_scope(element, bwb_id, extra_excl=excl),
            onderdelen=self._parse_onderdelen(element, bwb_id),
            voetnoten=self._noten(element, excl),
            illustraties=self._illustraties(element, extra_excl=excl),
        )
        for art in element.iterfind("artikel"):
            bijlage.artikelen.append(self._parse_artikel(art, bwb_id))
        return bijlage

    def _parse_artikel(self, element: etree._Element, bwb_id: str) -> Artikel:
        kop = element.find("kop")
        artikel = Artikel(
            id=self._knoop_id(bwb_id, element),
            nummer=self._tekst(kop.find("nr")) if kop is not None else "",
            label=element.get("label", ""),
            tekst=self._lichaamstekst(element, binnen_lid=False),
            jci=self._element_jci(element),
            label_id=element.get("label-id"),
            inwerking=element.get("inwerking"),
            bron=element.get("bron"),
            effect=element.get("effect"),
            status=element.get("status"),
            terugwerkend_tot=self._terugwerkend(element),
            wijzigingsbronnen=self._wijzigingsbronnen(element),
            verwijzingen=self._verwijzingen_scope(
                element, bwb_id, extra_excl=" and not(ancestor::lid) and not(ancestor::li)"
            ),
            onderdelen=self._parse_onderdelen(element, bwb_id),
            voetnoten=self._noten(element, " and not(ancestor::lid) and not(ancestor::li)"),
            illustraties=self._illustraties(
                element, extra_excl=" and not(ancestor::lid) and not(ancestor::li)"
            ),
        )
        for lid in element.iterfind("lid"):
            artikel.leden.append(self._parse_lid(lid, bwb_id))
        return artikel

    def _parse_lid(self, element: etree._Element, bwb_id: str) -> Lid:
        return Lid(
            id=self._knoop_id(bwb_id, element),
            nummer=self._tekst(element.find("lidnr")),
            tekst=self._lichaamstekst(element, binnen_lid=True),
            jci=self._element_jci(element),
            terugwerkend_tot=self._terugwerkend(element),
            verwijzingen=self._verwijzingen_scope(
                element, bwb_id, extra_excl=" and not(ancestor::li)"
            ),
            onderdelen=self._parse_onderdelen(element, bwb_id),
            voetnoten=self._noten(element, " and not(ancestor::li)"),
            definieert_begrippen=self._definities(element),
            illustraties=self._illustraties(element, extra_excl=" and not(ancestor::li)"),
        )

    # --------------------------------------------------------------- onderdelen
    def _parse_onderdelen(self, element: etree._Element, bwb_id: str) -> list[Onderdeel]:
        """Onderdelen uit direct geneste ``<lijst>/<li>`` (recursief)."""
        onderdelen: list[Onderdeel] = []
        for lijst in element.findall("lijst"):
            for li in lijst.findall("li"):
                onderdelen.append(self._parse_onderdeel(li, bwb_id))
        return onderdelen

    def _parse_onderdeel(self, li: etree._Element, bwb_id: str) -> Onderdeel:
        nr = li.find("li.nr")
        tekst_delen = [_tekst_zonder_noot(node) for node in li.xpath("./al")]
        return Onderdeel(
            id=self._knoop_id(bwb_id, li),
            nummer=self._tekst(nr) if nr is not None else "",
            tekst=re.sub(r"\s+", " ", " ".join(tekst_delen)).strip(),
            jci=self._element_jci(li),
            verwijzingen=self._verwijzingen_scope(li, bwb_id, base="./al//*"),
            subonderdelen=self._parse_onderdelen(li, bwb_id),
            voetnoten=[self._noot_tekst(noot) for noot in li.xpath("./al//noot")],
            definieert_begrippen=self._definities(li),
            illustraties=self._illustraties(li, base="./al//illustratie"),
        )

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _knoop_id(bwb_id: str, element: etree._Element) -> str:
        """Stabiele sleutel uit ``bwb-ng-variabel-deel`` (valt terug op tag)."""
        pad = element.get("bwb-ng-variabel-deel")
        return f"{bwb_id}{pad}" if pad else f"{bwb_id}/{element.tag}"

    @staticmethod
    def _tekst(element: etree._Element | None) -> str:
        """Genormaliseerde tekst van een element, exclusief meta-data-subtrees."""
        if element is None:
            return ""
        delen = element.xpath(".//text()[not(ancestor::meta-data)]")
        return re.sub(r"\s+", " ", "".join(delen)).strip()

    @staticmethod
    def _lichaamstekst(element: etree._Element, *, binnen_lid: bool) -> str:
        """Verzamel de lopende tekst (alinea's + lijstnummers) van een element.

        Sluit meta-data en voetnoten uit. Voor een artikel met leden wordt de
        tekst die in leden staat overgeslagen (die hoort bij het lid), zodat er
        geen dubbeling ontstaat. Tabellen (CALS) worden — buiten de alinea's om
        — als leesbare rijen ná de lopende tekst toegevoegd.
        """

        # Onderdeel-tekst (al binnen <li>) hoort bij het onderdeel-node, niet bij
        # het lid/artikel → uitsluiten zodat de full-text index niet dubbelt.
        # Alinea's binnen tabellen horen bij de tabelweergave.
        if binnen_lid:
            scope = "not(ancestor::li) and not(ancestor::meta-data)"
        else:
            scope = "not(ancestor::lid) and not(ancestor::li) and not(ancestor::meta-data)"
        delen = [
            _tekst_zonder_noot(node)
            for node in element.xpath(f".//al[{scope} and not(ancestor::table)]")
        ]
        tekst = re.sub(r"\s+", " ", " ".join(delen)).strip()
        tabellen = [_tabel_tekst(t) for t in element.xpath(f".//table[{scope}]")]
        tabellen = [t for t in tabellen if t]
        if tabellen:
            tekst = "\n".join([tekst, *tabellen]).strip()
        return tekst

    @staticmethod
    def _bijlage_tekst(element: etree._Element) -> str:
        """Eigen lopende tekst van een bijlage: alinea's die niet in een genest
        artikel/lid/onderdeel of tabel staan (die horen bij hun eigen node)."""
        scope = (
            "not(ancestor::artikel) and not(ancestor::lid) and not(ancestor::li)"
            " and not(ancestor::meta-data) and not(ancestor::table)"
        )
        delen = [_tekst_zonder_noot(al) for al in element.xpath(f".//al[{scope}]")]
        tekst = re.sub(r"\s+", " ", " ".join(delen)).strip()
        tabellen = [
            _tabel_tekst(t)
            for t in element.xpath(
                ".//table[not(ancestor::artikel) and not(ancestor::lid) and not(ancestor::li)]"
            )
        ]
        tabellen = [t for t in tabellen if t]
        if tabellen:
            tekst = "\n".join([tekst, *tabellen]).strip()
        return tekst

    @staticmethod
    def _illustraties(
        element: etree._Element,
        *,
        base: str = ".//illustratie",
        extra_excl: str = "",
    ) -> list[Illustratie]:
        """Illustraties binnen ``element`` (uit ``<plaatje>/<illustratie>``),
        beperkt via ``base`` + exclusies zoals de tekst-scope, zodat een
        illustratie bij de meest specifieke tekstdrager landt."""
        out: list[Illustratie] = []
        for il in element.xpath(f"{base}[not(ancestor::meta-data){extra_excl}]"):
            out.append(
                Illustratie(
                    id=il.get("id") or il.get("naam") or "",
                    naam=il.get("naam"),
                    formaat=il.get("formaat"),
                    breedte=il.get("breedte"),
                    hoogte=il.get("hoogte"),
                    alt=il.get("alt"),
                )
            )
        return out

    def _parse_ondertekenaars(self, wetgeving: etree._Element) -> list[Ondertekenaar]:
        """Ondertekenaars uit de ``<ondertekening>``-blokken van de regeling.

        Een ondertekening bevat een ``<functie>`` en een ``<naam>`` (met
        ``<voornaam>``/``<achternaam>``). Ontdubbelt op (functie, naam)."""
        gezien: set[tuple[str, str, str]] = set()
        out: list[Ondertekenaar] = []
        for ondt in wetgeving.iter("ondertekening"):
            naam_el = ondt.find("naam")
            functie = self._tekst(ondt.find("functie")) or None
            voornaam = self._tekst(naam_el.find("voornaam")) if naam_el is not None else ""
            achternaam = self._tekst(naam_el.find("achternaam")) if naam_el is not None else ""
            naam = self._tekst(naam_el) if naam_el is not None else ""
            if not (functie or naam):
                continue
            sleutel = (functie or "", naam, achternaam)
            if sleutel in gezien:
                continue
            gezien.add(sleutel)
            out.append(
                Ondertekenaar(
                    functie=functie,
                    naam=naam or None,
                    voornaam=voornaam or None,
                    achternaam=achternaam or None,
                    plaats=self._tekst(ondt.find("plaats")) or None,
                    datum=None,
                )
            )
        return out

    @staticmethod
    def _divisie_tekst(element: etree._Element) -> str:
        """Lopende tekst van een divisie: alinea's in ``./tekst``.

        Sluit alinea's binnen onderdelen (``<li>``), voetnoten en meta-data
        uit; geneste subdivisies staan buiten ``./tekst`` en tellen dus niet mee.
        """
        xpath = (
            "./tekst//al[not(ancestor::li) and not(ancestor::meta-data)"
            " and not(ancestor::table)]"
        )
        delen = [_tekst_zonder_noot(node) for node in element.xpath(xpath)]
        return re.sub(r"\s+", " ", " ".join(delen)).strip()

    def _wet_aanhef(self, wetgeving: etree._Element) -> dict[str, str | None]:
        """Aanhef en considerans (``wet-besluit/aanhef`` of ``regeling/aanhef``)."""
        aanhef_el = wetgeving.find("wet-besluit/aanhef")
        if aanhef_el is None:
            aanhef_el = wetgeving.find("regeling/aanhef")
        if aanhef_el is None:
            return {"aanhef": None, "considerans": None}
        aanhef_delen = [
            # Wetten/besluiten openen met <wij>, ministeriële regelingen met <wie>.
            self._tekst(aanhef_el.find("wij")),
            self._tekst(aanhef_el.find("wie")),
            self._tekst(aanhef_el.find("afkondiging")),
        ]
        aanhef = " ".join(d for d in aanhef_delen if d).strip() or None
        considerans_delen = [
            _tekst_zonder_noot(al) for al in aanhef_el.xpath("./considerans/considerans.al")
        ]
        considerans = re.sub(r"\s+", " ", " ".join(considerans_delen)).strip() or None
        return {"aanhef": aanhef, "considerans": considerans}

    def _noten(self, element: etree._Element, extra_excl: str) -> list[str]:
        """Voetnoten binnen het tekstbereik van deze node (zelfde exclusies
        als de lopende tekst, zodat noot en tekst op hetzelfde niveau landen)."""
        xpath = f".//noot[not(ancestor::meta-data){extra_excl}]"
        return [self._noot_tekst(noot) for noot in element.xpath(xpath)]

    @staticmethod
    def _noot_tekst(noot: etree._Element) -> str:
        delen = noot.xpath(".//text()[not(ancestor::meta-data)]")
        return re.sub(r"\s+", " ", "".join(delen)).strip()

    @staticmethod
    def _definities(element: etree._Element) -> list[str]:
        """Gedefinieerde begrippen: cursieve termen (``nadruk type="cur"``)
        die op een dubbele punt eindigen, aan het begin van een definitie."""
        begrippen: list[str] = []
        for term in element.xpath("./al/nadruk[@type='cur']/text()"):
            genormaliseerd = term.strip()
            if genormaliseerd.endswith(":"):
                begrippen.append(genormaliseerd.rstrip(":").strip())
        return begrippen

    @staticmethod
    def _element_jci(element: etree._Element) -> str | None:
        """De canonieke ``jci1.3``-verwijzing van een artikel/lid uit zijn meta-data."""
        for jci in element.xpath("./meta-data/jcis/jci/@verwijzing"):
            if jci.startswith("jci1.3:"):
                return jci
        return None

    @staticmethod
    def _verwijzingen_scope(
        element: etree._Element,
        bwb_id: str,
        *,
        base: str = ".//*",
        extra_excl: str = "",
    ) -> list[Verwijzing]:
        """Verwijzingen binnen ``element``, beperkt via ``base`` + extra exclusies.

        ``base`` bepaalt het zoekbereik (bv. ``./al//*`` voor alleen de directe
        alinea's van een onderdeel); ``extra_excl`` voegt voorwaarden toe zoals
        ``and not(ancestor::lid)`` om geneste niveaus uit te sluiten.
        """
        scope = etree.Element("scope")
        xpath = f"{base}[self::intref or self::extref][not(ancestor::meta-data){extra_excl}]"
        for ref in element.xpath(xpath):
            scope.append(_kopie(ref))
        return extract_references(scope, eigen_bwb_id=bwb_id)

    @staticmethod
    def _terugwerkend(element: etree._Element) -> str | None:
        """Retroactieve ingangsdatum uit het eigen meta-data-blok
        (``brondata/inwerkingtreding/terugwerkend.datum``), indien aanwezig."""
        for datum in element.xpath(
            "./meta-data/brondata/inwerkingtreding/terugwerkend.datum/@isodatum"
        ):
            if datum:
                return datum
        return None

    @staticmethod
    def _wijzigingsbronnen(element: etree._Element) -> list[str]:
        """Stb-bronnen waarmee dit artikel is gewijzigd (uit ``<juncto>``)."""
        bronnen: list[str] = []
        for pub in element.xpath("./meta-data//juncto/publicatie"):
            jaar = pub.findtext("publicatiejaar")
            nr = pub.findtext("publicatienr")
            if jaar and nr:
                bronnen.append(f"{pub.get('soort', 'Stb')}.{jaar}-{nr}")
        return bronnen

    @staticmethod
    def _wet_brondata(wetgeving: etree._Element) -> dict[str, str | None]:
        """Brondata van de oorspronkelijke regeling (wetgeving/meta-data/brondata)."""
        pub = wetgeving.find("meta-data/brondata/oorspronkelijk/publicatie")
        if pub is None:
            return {
                "publicatiejaar": None,
                "publicatienr": None,
                "ondertekeningsdatum": None,
                "uitgiftedatum": None,
                "dossier": None,
            }
        ondt = pub.find("ondertekeningsdatum")
        uitg = pub.find("uitgiftedatum")
        doss = pub.find("dossierref")
        return {
            "publicatiejaar": pub.findtext("publicatiejaar"),
            "publicatienr": pub.findtext("publicatienr"),
            "ondertekeningsdatum": ondt.get("isodatum") if ondt is not None else None,
            "uitgiftedatum": uitg.get("isodatum") if uitg is not None else None,
            "dossier": doss.get("dossier") if doss is not None else None,
        }


def _tekst_zonder_noot(element: etree._Element) -> str:
    """Alle tekst van een element, exclusief voetnoot-inhoud (``<noot>``)."""
    return "".join(element.xpath(".//text()[not(ancestor::noot)]"))


def _tabel_tekst(table: etree._Element) -> str:
    """Leesbare weergave van een CALS-tabel: cellen per rij met ``|`` gescheiden.

    De structuur (kolombreedtes, spans) gaat verloren; doel is dat geen tekst
    stilzwijgend verdwijnt en de inhoud full-text-doorzoekbaar is.
    """
    rijen: list[str] = []
    for row in table.xpath(".//row"):
        cellen: list[str] = []
        for entry in row.xpath("./entry"):
            delen = entry.xpath(".//text()[not(ancestor::meta-data) and not(ancestor::noot)]")
            cellen.append(re.sub(r"\s+", " ", "".join(delen)).strip())
        rij = " | ".join(cellen).strip()
        if rij.strip("| "):
            rijen.append(rij)
    return "\n".join(rijen)


def _kopie(element: etree._Element) -> etree._Element:
    """Maak een losse kopie van een element (zonder het uit de boom te halen)."""
    nieuw = etree.Element(element.tag, dict(element.attrib))
    nieuw.text = element.text
    for child in element:
        nieuw.append(_kopie(child))
    return nieuw
