"""Dataclasses voor het BWB-domeinmodel.

Het model volgt de geverifieerde toestand-XML-structuur:
``toestand -> wetgeving -> wet-besluit -> wettekst -> hoofdstuk/afdeling/
paragraaf -> artikel -> lid``. Verwijzingen komen primair uit de
gestructureerde ``<intref>``/``<extref>``-elementen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class VerwijzingSoort(StrEnum):
    """Interne verwijzing (binnen dezelfde wet), externe (andere regeling) of
    een uit lopende tekst gedetecteerde (ongetagde) verwijzing."""

    INTERN = "intref"
    EXTERN = "extref"
    TEKSTUEEL = "tekstueel"


@dataclass(slots=True)
class Verwijzing:
    """Een gestructureerde of gedetecteerde verwijzing vanuit een tekstdeel."""

    soort: VerwijzingSoort
    tekst: str
    doel_bwb_id: str | None = None
    doel_pad: str | None = None  # bwb-ng-variabel-deel van het doel
    doc: str | None = None  # jci-verwijzing, bv. "jci1.3:c:BWBR0004770&artikel=4"
    verwijzing_id: str | None = None  # bron-id van de <intref>/<extref>
    doel_artikel: str | None = None  # artikelnummer bij tekstuele detectie


@dataclass(slots=True)
class Illustratie:
    """Een ``<illustratie>`` (binnen ``<plaatje>``): een afbeelding met alleen
    attributen (geen tekst). Hangt aan de dichtstbijzijnde tekstdrager."""

    id: str
    naam: str | None = None  # bestandsnaam, bv. "123954.png"
    formaat: str | None = None  # bv. "png"
    breedte: str | None = None  # bv. "1417px"
    hoogte: str | None = None  # bv. "364px"
    alt: str | None = None  # alternatieve tekst/bijschrift, indien aanwezig


@dataclass(slots=True)
class Onderdeel:
    """Een onderdeel (``<li>``) binnen een ``<lijst>``; bv. een definitie of
    opsommingspunt. Kan genest zijn (sub-lijsten) en eigen verwijzingen dragen.
    """

    id: str
    nummer: str  # uit <li.nr>, bv. "a." of "1."
    tekst: str
    jci: str | None = None  # canonieke jci (tot onderdeel-niveau, &o=…)
    verwijzingen: list[Verwijzing] = field(default_factory=list)
    subonderdelen: list[Onderdeel] = field(default_factory=list)
    voetnoten: list[str] = field(default_factory=list)
    definieert_begrippen: list[str] = field(default_factory=list)  # uit <nadruk type="cur">…:
    illustraties: list[Illustratie] = field(default_factory=list)


@dataclass(slots=True)
class Lid:
    """Een lid binnen een artikel."""

    id: str
    nummer: str
    tekst: str
    jci: str | None = None  # canonieke jci (tot lid-niveau) uit meta-data
    terugwerkend_tot: str | None = None  # retroactieve ingangsdatum (ISO), indien aanwezig
    verwijzingen: list[Verwijzing] = field(default_factory=list)
    onderdelen: list[Onderdeel] = field(default_factory=list)
    voetnoten: list[str] = field(default_factory=list)
    definieert_begrippen: list[str] = field(default_factory=list)
    illustraties: list[Illustratie] = field(default_factory=list)


@dataclass(slots=True)
class Artikel:
    """Een artikel; kan leden bevatten of directe tekst."""

    id: str
    nummer: str
    label: str
    tekst: str
    jci: str | None = None  # canonieke jci-verwijzing uit meta-data
    label_id: str | None = None  # WTI-join-sleutel (label-id-attribuut)
    # Provenance/temporaliteit uit de artikel-attributen.
    inwerking: str | None = None  # datum inwerkingtreding (ISO)
    bron: str | None = None  # bv. "Stb.2009-265"
    effect: str | None = None  # "wijziging" | "nieuwe-regeling" | ...
    status: str | None = None  # bv. "goed"
    terugwerkend_tot: str | None = None  # retroactieve ingangsdatum (ISO), indien aanwezig
    wijzigingsbronnen: list[str] = field(default_factory=list)  # <juncto> Stb-refs
    leden: list[Lid] = field(default_factory=list)
    verwijzingen: list[Verwijzing] = field(default_factory=list)
    onderdelen: list[Onderdeel] = field(default_factory=list)
    voetnoten: list[str] = field(default_factory=list)
    illustraties: list[Illustratie] = field(default_factory=list)


@dataclass(slots=True)
class Divisie:
    """Een ``<circulaire.divisie>`` uit een circulaire/beleidsregel.

    Anders dan een wettekst-structuurdeel is een divisie tegelijk *container*
    (geneste subdivisies) én *tekstdrager* (eigen alinea's). Ze draagt eigen
    provenance-attributen en verwijzingen en doet daarmee — net als een
    :class:`Artikel` — mee in het citatienetwerk (MERGE op ``ref_key``).
    """

    id: str
    nummer: str
    label: str
    titel: str
    tekst: str
    jci: str | None = None
    inwerking: str | None = None
    bron: str | None = None
    effect: str | None = None
    status: str | None = None
    terugwerkend_tot: str | None = None  # retroactieve ingangsdatum (ISO), indien aanwezig
    wijzigingsbronnen: list[str] = field(default_factory=list)
    verwijzingen: list[Verwijzing] = field(default_factory=list)
    onderdelen: list[Onderdeel] = field(default_factory=list)
    subdivisies: list[Divisie] = field(default_factory=list)
    voetnoten: list[str] = field(default_factory=list)
    illustraties: list[Illustratie] = field(default_factory=list)


@dataclass(slots=True)
class Bijlage:
    """Een ``<bijlage>`` van een regeling (direct kind van ``<wet-besluit>``/
    ``<regeling>``, ná de wettekst).

    Net als een :class:`Divisie` is een bijlage tegelijk *container* (kan eigen
    artikelen en onderdelen bevatten) én *tekstdrager* (eigen alinea's). Ze draagt
    provenance-attributen en doet — via ``ref_key`` — mee in het citatienetwerk.
    """

    id: str
    nummer: str
    label: str
    titel: str
    tekst: str
    jci: str | None = None
    inwerking: str | None = None
    bron: str | None = None
    effect: str | None = None
    status: str | None = None
    terugwerkend_tot: str | None = None  # retroactieve ingangsdatum (ISO), indien aanwezig
    wijzigingsbronnen: list[str] = field(default_factory=list)
    verwijzingen: list[Verwijzing] = field(default_factory=list)
    artikelen: list[Artikel] = field(default_factory=list)
    onderdelen: list[Onderdeel] = field(default_factory=list)
    voetnoten: list[str] = field(default_factory=list)
    illustraties: list[Illustratie] = field(default_factory=list)


@dataclass(slots=True)
class Ondertekenaar:
    """Een ondertekenaar van de regeling (uit ``<ondertekening>``): de functie en
    de naam van de persoon die de regeling heeft ondertekend. Wordt over wetten
    heen ontdubbeld op (functie, naam)."""

    functie: str | None = None  # bv. "De Staatssecretaris van Financiën"
    naam: str | None = None  # volledige naam
    voornaam: str | None = None
    achternaam: str | None = None
    plaats: str | None = None
    datum: str | None = None  # ondertekeningsdatum (ISO), indien aanwezig


@dataclass(slots=True)
class Structuurdeel:
    """Generiek structuurdeel: hoofdstuk, afdeling of paragraaf.

    ``soort`` bepaalt het structuurlabel (Hoofdstuk/Afdeling/Paragraaf) en de
    relatie naar de ouder (heeftHoofdstuk/heeftAfdeling/heeftParagraaf).
    Structuurdelen kunnen genest zijn en artikelen bevatten.
    """

    id: str
    soort: str  # "hoofdstuk" | "titeldeel" | "afdeling" | "paragraaf"
    nummer: str
    label: str
    titel: str
    jci: str | None = None  # canonieke jci van het structuurdeel
    label_id: str | None = None  # WTI-join-sleutel (label-id-attribuut)
    subdelen: list[Structuurdeel] = field(default_factory=list)
    artikelen: list[Artikel] = field(default_factory=list)


@dataclass(slots=True)
class Wet:
    """De wortel van het model: een regeling/wet."""

    bwb_id: str
    citeertitel: str
    opschrift: str
    soort: str
    geldig_vanaf: str | None = None
    geldig_tot: str | None = None
    label_id: str | None = None  # WTI-join-sleutel (label-id van <wetgeving>)
    # Toestand-identiteit (root-attr bwb-ng-vast-deel), bv.
    # "http://wetten.overheid.nl/id/BWBR0004770/2026-01-01/0".
    vast_deel_url: str | None = None
    aanhef: str | None = None  # <wij> + <afkondiging>
    considerans: str | None = None  # overwegingen uit de aanhef
    # Brondata van de oorspronkelijke regeling (wetgeving/meta-data/brondata).
    publicatiejaar: str | None = None
    publicatienr: str | None = None
    ondertekeningsdatum: str | None = None  # ISO
    uitgiftedatum: str | None = None  # ISO
    dossier: str | None = None
    structuurdelen: list[Structuurdeel] = field(default_factory=list)
    losse_artikelen: list[Artikel] = field(default_factory=list)
    # Circulaires/beleidsregels hebben geen wettekst maar een divisie-boom.
    divisies: list[Divisie] = field(default_factory=list)
    # Bijlagen staan náást de wettekst (kind van <wet-besluit>/<regeling>).
    bijlagen: list[Bijlage] = field(default_factory=list)
    # Ondertekenaars van de regeling (Fase 1b).
    ondertekenaars: list[Ondertekenaar] = field(default_factory=list)


@dataclass(slots=True)
class ToestandRef:
    """Verwijzing naar één toestand (versie) van een regeling, uit de SRU-index."""

    bwb_id: str
    locatie_toestand: str
    geldig_vanaf: str | None = None
    geldig_tot: str | None = None
    zicht_vanaf: str | None = None
    zicht_tot: str | None = None
    locatie_wti: str | None = None
    locatie_manifest: str | None = None


@dataclass(slots=True)
class ImportResult:
    """Uitkomst van één wet binnen een (batch-)import."""

    bwb_id: str
    ok: bool
    overzicht: ImportSummary | None = None
    fout: str | None = None

    def as_dict(self) -> dict:
        return {
            "bwb_id": self.bwb_id,
            "status": "ok" if self.ok else "fout",
            "overzicht": self.overzicht.as_dict() if self.overzicht else None,
            "fout": self.fout,
        }


@dataclass(slots=True)
class ImportSummary:
    """Telling van geïmporteerde elementen, getoond na een import."""

    bwb_id: str
    wetten: int = 0
    hoofdstukken: int = 0
    titeldelen: int = 0
    afdelingen: int = 0
    paragrafen: int = 0
    divisies: int = 0
    bijlagen: int = 0
    artikelen: int = 0
    leden: int = 0
    onderdelen: int = 0
    illustraties: int = 0
    ondertekenaars: int = 0
    relaties: int = 0

    def as_dict(self) -> dict[str, int | str]:
        return {
            "bwb_id": self.bwb_id,
            "wetten": self.wetten,
            "hoofdstukken": self.hoofdstukken,
            "titeldelen": self.titeldelen,
            "afdelingen": self.afdelingen,
            "paragrafen": self.paragrafen,
            "divisies": self.divisies,
            "bijlagen": self.bijlagen,
            "artikelen": self.artikelen,
            "leden": self.leden,
            "onderdelen": self.onderdelen,
            "illustraties": self.illustraties,
            "ondertekenaars": self.ondertekenaars,
            "relaties": self.relaties,
        }
