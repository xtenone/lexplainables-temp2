"""
Contracten voor het annotatie-domein (wetsanalyse-workbench).

Bewust **los** van `contracts.py` (de analyse-job/skill-contracten): dit is een vers, toekomstvast
domein. Review-klaar ontworpen — velden voor latere fasen (aandacht, diff, alternatieven, lifecycle,
review_reason) zitten er vanaf het begin in. De JAS-klassenamen worden gevalideerd tegen de canonieke
`validation.GELDIGE_JAS_KLASSEN` (neutrale data, geen skill-werkstroom) — dat gebeurt in de router.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from .db import utcnow


# --- enums -------------------------------------------------------------------

class DocumentStatus(str, Enum):
    in_review = "in_review"
    geaccordeerd = "geaccordeerd"
    gepromoveerd = "gepromoveerd"


class Lifecycle(str, Enum):
    voorgesteld = "voorgesteld"
    critic_checked = "critic_checked"
    human_approved = "human_approved"
    edited = "edited"
    rejected = "rejected"
    published = "published"
    reused = "reused"


class BeslissingType(str, Enum):
    approve = "approve"
    edit = "edit"
    reject = "reject"
    comment = "comment"


class ReviewReason(str, Enum):
    verkeerde_klasse = "verkeerde_klasse"
    bron_gemist = "bron_gemist"
    tekst = "tekst"
    interpretatie = "interpretatie"
    onvoldoende_context = "onvoldoende_context"
    anders = "anders"


class Aandacht(str, Enum):
    groen = "groen"
    geel = "geel"
    rood = "rood"


# --- domein ------------------------------------------------------------------

class Alternatief(BaseModel):
    """Kandidaat-klasse bij twijfel (disambiguatie)."""

    klasse: str
    motivatie: str = ""


class Beslissing(BaseModel):
    """Eén human-decision op een element."""

    type: BeslissingType
    actor: str = ""
    tijd: datetime = Field(default_factory=utcnow)
    review_reason: ReviewReason | None = None
    comment: str = ""
    wijziging: dict = {}   # bij een edit: de gewijzigde velden (klasse/tekst/toelichting/lid)


class AnnotatieElement(BaseModel):
    """Eén JAS-annotatie-element met zijn review-levenscyclus."""

    id: str
    klasse: str
    tekst: str
    lid: str = ""
    toelichting: str = ""
    vindplaats: str = ""
    span: list[int] | None = None
    herkomst: str = "agent"    # agent | mens
    lifecycle: Lifecycle = Lifecycle.voorgesteld
    alternatieven: list[Alternatief] = []
    aandacht: Aandacht | None = None
    critic: str = ""           # korte Critic-motivatie bij het aandacht-niveau
    diff: dict = {}            # bij een edit: {veld: {"voor": ..., "na": ...}}
    beslissingen: list[Beslissing] = []


class AnnotatieDocument(BaseModel):
    """Annotaties per bron (bwbId+artikel[+lid]) binnen een werkgebied."""

    slug: str
    client_id: str = ""
    werkgebied: str = ""
    bwbId: str
    artikel: str
    lid: str = ""
    status: DocumentStatus = DocumentStatus.in_review
    elementen: list[AnnotatieElement] = []
    created: datetime | None = None
    updated: datetime | None = None


class AuditRecord(BaseModel):
    """Append-only auditregel; render-baar als tijdlijn."""

    id: int | None = None
    actor: str = ""
    actie: str
    element_id: str | None = None
    detail: dict = {}
    tijdstip: datetime | None = None


# --- invoer / uitvoer --------------------------------------------------------

class DocumentCreate(BaseModel):
    bwbId: str
    artikel: str
    lid: str | None = None
    werkgebied: str = ""


class ElementInvoer(BaseModel):
    """Eén voorgesteld element (van de agent), zoals de workbench het doorstuurt."""

    klasse: str
    tekst: str
    lid: str = ""
    toelichting: str = ""
    vindplaats: str = ""
    span: list[int] | None = None
    alternatieven: list[Alternatief] = []
    aandacht: Aandacht | None = None   # Critic-oordeel (groen|geel|rood); None = geen Critic-pas
    critic: str = ""                   # korte Critic-motivatie


class ElementenInvoer(BaseModel):
    elementen: list[ElementInvoer]


class Wijziging(BaseModel):
    """Voorgestelde veldwijzigingen bij een edit-beslissing (alle optioneel)."""

    klasse: str | None = None
    tekst: str | None = None
    toelichting: str | None = None
    lid: str | None = None


class BeslissingInvoer(BaseModel):
    type: BeslissingType
    review_reason: ReviewReason | None = None
    comment: str = ""
    wijziging: Wijziging | None = None


class DocumentSamenvatting(BaseModel):
    slug: str
    bwbId: str
    artikel: str
    lid: str = ""
    werkgebied: str = ""
    status: DocumentStatus
    aantal_elementen: int
    updated: datetime | None = None
