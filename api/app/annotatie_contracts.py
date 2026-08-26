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

from pydantic import BaseModel, Field, ValidationError, model_validator

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
    heropen = "heropen"


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


#: Lifecycles waarin het element een eindoordeel van de jurist draagt en dus op slot gaat: wijzigen
#: kan pas na een expliciete `heropen`-beslissing. `edited` hoort er bewust NIET bij — een klasse
#: wijzigen en er daarna een toelichting bij typen moet één doorlopende handeling blijven. Geldt
#: alleen voor agent-elementen: een eigen markering is `human_approved` bij het aanmaken en is
#: daarmee gemaakt, niet beoordeeld.
VERGRENDELDE_LIFECYCLES: frozenset[Lifecycle] = frozenset({
    Lifecycle.human_approved,
    Lifecycle.rejected,
})


# --- domein ------------------------------------------------------------------

class AgentRun(BaseModel):
    """Wie/wat een agent-ronde produceerde — de provenance van een voorstel.

    Zonder dit is achteraf niet vast te stellen mét welk model een markering tot stand kwam, en
    dat is precies wat een export moet dragen en wat de latere graaf-promotie als herkomst nodig
    heeft. Het hangt op twee plekken: op het document (het volledige spoor van alle rondes) en op
    het element zelf, want tussen twee beurten kan het geconfigureerde model wisselen.
    """

    ronde: int = 0
    model: str = ""              # bv. "claude-sonnet-4-6"
    provider: str = ""
    agent_versie: str = ""
    critic_rondes: int = 0       # aantal herzieningen in deze beurt
    stop_reden: str = ""         # waaróm de annotatielus eindigde
    tijd: datetime = Field(default_factory=utcnow)


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


class CriticRonde(BaseModel):
    """Eén Critic-oordeel binnen de herzieningslus, met de instructie die eruit volgde.

    Een lijst hiervan (analoog aan `beslissingen`) maakt het heen-en-weer tussen annoteerder en
    Critic zichtbaar: 'ronde 1 rood, klasse te grof → ronde 2 aangepast naar Voorwaarde'. Een
    enkelvoudige `aandacht`/`critic` zou elke ronde overschrijven en dat spoor wissen.
    """

    ronde: int
    aandacht: Aandacht | None = None
    motivatie: str = ""
    actie: str = "behoud"          # behoud | vervang | verwijder
    # Is de instructie ook uitgevoerd? Sinds de correctie in code gebeurt (graph-qa's patcher) is dat
    # een ander feit dan "de Critic stelde het voor", en het auditspoor hoort ze te onderscheiden.
    toegepast: bool = False
    voorstel_klasse: str = ""
    voorstel_tekst: str = ""
    tijd: datetime = Field(default_factory=utcnow)


class CriticSuggestie(BaseModel):
    """Critic-oordeel als advies: nooit automatisch toegepast, altijd een klik van de jurist.

    Twee bronnen: een oordeel over een markering die de jurist zelf maakte, en een fragmentvoorstel
    uit de eindbeoordeling van de agent — die komt te laat voor de patcher en zou anders alleen in de
    motivatietekst blijven staan."""

    aandacht: Aandacht | None = None
    motivatie: str = ""
    voorstel_klasse: str = ""
    voorstel_tekst: str = ""
    status: str = "open"           # open | geaccepteerd | afgewezen
    tijd: datetime = Field(default_factory=utcnow)


class Anker(BaseModel):
    """Waar een fragment stond toen het werd gemaakt.

    Twee selectors naast elkaar (het W3C-annotatiepatroon): exacte offsets voor precisie — nodig om
    twee identieke fragmenten in één artikel te onderscheiden — en quote-met-context als de brontekst
    schuift (herimport, ander lid-bereik). `bron_hash` vertelt of de offsets nog over dezelfde tekst
    gaan. De offsets slaan op de samengevoegde brontekst die het documentpaneel toont.
    """

    lid: str = ""
    start: int = 0
    eind: int = 0
    voor: str = ""        # tot 48 tekens context vóór het fragment
    na: str = ""          # tot 48 tekens context erna
    bron_hash: str = ""   # sha256 van de brontekst, ingekort


class AnnotatieElement(BaseModel):
    """Eén JAS-annotatie-element met zijn review-levenscyclus."""

    id: str
    klasse: str
    tekst: str
    lid: str = ""
    toelichting: str = ""
    vindplaats: str = ""
    # `herkomst` is ONVERANDERLIJK: wie het element heeft aangemaakt. `gewijzigd_door` is wie het
    # daarna inhoudelijk aanpaste. Die twee zijn bewust gescheiden — anders is niet meer te zien of
    # een element van de agent kwam zodra de jurist het één keer bijstelt.
    herkomst: str = "agent"        # agent | mens — aangemaakt door
    gewijzigd_door: str = ""       # "" | agent | mens — laatst inhoudelijk gewijzigd door
    lifecycle: Lifecycle = Lifecycle.voorgesteld
    alternatieven: list[Alternatief] = []
    aandacht: Aandacht | None = None
    critic: str = ""           # korte Critic-motivatie bij het aandacht-niveau (laatste ronde)
    critic_rondes: list[CriticRonde] = []
    critic_suggestie: CriticSuggestie | None = None   # alleen bij herkomst == "mens"
    anker: Anker | None = None
    geproduceerd_door: AgentRun | None = None   # None = agent-ronde van vóór de registratie, of mens
    diff: dict = {}            # bij een edit: {veld: {"voor": ..., "na": ...}}
    beslissingen: list[Beslissing] = []

    @model_validator(mode="after")
    def _herstel_herkomst(self):
        """Repareer rijen van vóór de scheiding tussen aanmaken en wijzigen.

        Tot dan zette een edit `herkomst` op "mens", terwijl de jurist toen nog helemaal geen
        elementen kón aanmaken. Zo'n element is dus agent-gemaakt en mens-gewijzigd. De reparatie is
        lazy (draait bij elke `model_validate`) en alleen-vooruit: zonder beslissingen blijft
        "mens" gewoon staan, want dat is dan een echt door de jurist aangemaakt element.
        """
        if not self.gewijzigd_door and self.herkomst == "mens" and self.beslissingen:
            object.__setattr__(self, "herkomst", "agent")
            object.__setattr__(self, "gewijzigd_door", "mens")
        return self


class AnnotatieDocument(BaseModel):
    """Annotaties per bron (bwbId+artikel[+lid]) binnen een werkgebied."""

    slug: str
    user_id: str = ""       # eigenaar (ingelogde gebruiker); de zichtbaarheid gaat hierop
    client_id: str = ""      # bearer-client (herkomst/tenant)
    # De naam van de regeling zoals hij in beeld komt. Apart van `werkgebied`, dat een
    # kennisdomein hoort te zijn — de werkplek zette de wetnaam daar eerder in.
    citeertitel: str = ""
    werkgebied: str = ""
    bwbId: str
    artikel: str
    lid: str = ""
    status: DocumentStatus = DocumentStatus.in_review
    elementen: list[AnnotatieElement] = []
    runs: list[AgentRun] = []   # het productiespoor: elke agent-ronde die aan dit document werkte
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
    citeertitel: str = ""
    werkgebied: str = ""


class ElementInvoer(BaseModel):
    """Eén voorgesteld element (van de agent), zoals de workbench het doorstuurt."""

    # Het id van de agent. Is het bekend, dan matcht de merge daarop en blijven beslissingen en
    # levenscyclus intact; ontbreekt het (oudere client), dan valt de merge terug op de tekst.
    id: str | None = None
    klasse: str
    tekst: str
    lid: str = ""
    toelichting: str = ""
    vindplaats: str = ""
    alternatieven: list[Alternatief] = []
    aandacht: Aandacht | None = None   # Critic-oordeel (groen|geel|rood); None = geen Critic-pas
    critic: str = ""                   # korte Critic-motivatie
    critic_rondes: list[CriticRonde] = []
    anker: Anker | None = None


class SuggestieInvoer(BaseModel):
    """Kanttekening van de Critic: bij een element dat de JURIST maakte, of — als er een concreet
    voorstel in zit (klasse en/of fragment) — bij een agent-element waarvan de eindbeoordeling nog
    iets voorstelt."""

    element_id: str
    aandacht: Aandacht | None = None
    motivatie: str = ""
    voorstel_klasse: str = ""
    voorstel_tekst: str = ""


class ElementenInvoer(BaseModel):
    """De volledige uitkomst van één agent-ronde voor dit document.

    **Eén kapot element mag de rest niet meeslepen.** De merge in de handler verwerpt een element met
    een ongeldige klasse of een leeg fragment al per stuk, met een teller — maar de request-validatie
    ervóór was alles-of-niets, dus een schemafout leverde een 422 op en dan landde er níéts. Twee
    poorten met tegengesteld beleid: dat verschil was de fout, niet de strengheid. Op dev kostte het
    een complete annotatie van vijftien markeringen.

    Wat het schema niet haalt gaat daarom naar `geweigerd` in plaats van het verzoek te laten
    sneuvelen. De handler telt het op bij `verworpen`, zodat er precies één begrip "verworpen" is en
    de aanroeper het te horen krijgt.
    """

    elementen: list[ElementInvoer]
    #: Aangeboden elementen die het schema niet haalden, met de reden. Alleen gevuld door de
    #: validator hieronder; een client die dit zelf meestuurt, ziet het overschreven worden.
    geweigerd: list[dict] = []
    # Oordelen over MENS-elementen komen hier binnen, niet in `elementen`: die zijn bevroren en
    # mogen niet als voorstel terugkomen. Ze landen in `critic_suggestie` — advies, geen wijziging.
    suggesties: list[SuggestieInvoer] = []
    ronde: int = 0
    # De productiegegevens van deze ronde (model/provider/agentversie), zoals graph-qa ze in het
    # `run`-event meestuurt. Ontbreekt hij (oudere client), dan blijft het spoor leeg in plaats van
    # dat er iets wordt aangenomen.
    run: AgentRun | None = None
    # Agent-elementen die in deze ronde niet meer voorkomen: intrekken (default) of laten staan.
    # Elementen van de jurist en elementen met een beslissing worden nooit ingetrokken.
    trek_ontbrekende_in: bool = True

    @model_validator(mode="before")
    @classmethod
    def _weiger_per_element(cls, data: object) -> object:
        """Valideer `elementen` stuk voor stuk in plaats van als geheel. Zie de klasse-docstring.

        Alleen de lijst zelf wordt zo behandeld: is `elementen` geen lijst, of gaat er iets mis in
        een ánder veld, dan blijft het een gewone 422. Dit is een uitzondering voor de plek waar
        gedeeltelijk slagen beter is dan helemaal niet, geen algemene versoepeling.
        """
        if not isinstance(data, dict) or not isinstance(data.get("elementen"), list):
            return data
        goed, geweigerd = [], []
        for rauw in data["elementen"]:
            try:
                goed.append(ElementInvoer.model_validate(rauw))
            except ValidationError as fout:
                geweigerd.append({
                    "tekst": (rauw or {}).get("tekst", "") if isinstance(rauw, dict) else "",
                    "klasse": (rauw or {}).get("klasse", "") if isinstance(rauw, dict) else "",
                    "reden": "; ".join(
                        f"{'.'.join(str(x) for x in f['loc'])}: {f['msg']}" for f in fout.errors()[:3]
                    ),
                })
        return {**data, "elementen": goed, "geweigerd": geweigerd}


class MensElementInvoer(BaseModel):
    """Eén element dat de JURIST zelf aanmaakt (tekstselectie in het documentpaneel)."""

    klasse: str
    tekst: str
    lid: str = ""
    toelichting: str = ""
    vindplaats: str = ""
    anker: Anker | None = None


class Wijziging(BaseModel):
    """Voorgestelde veldwijzigingen bij een edit-beslissing (alle optioneel).

    Het `anker` hoort bij `tekst`: kort de jurist een markering in of breidt hij hem uit, dan schuift
    de plek mee. Blijft het oude anker staan, dan wijzen de offsets naar het oude fragment en springt
    de markering na herladen naar een ander voorkomen. Verandert de tekst zonder dat er een anker
    meekomt, dan wordt het oude gewist — geen anker is eerlijker dan een anker dat liegt.
    """

    klasse: str | None = None
    tekst: str | None = None
    toelichting: str | None = None
    lid: str | None = None
    anker: Anker | None = None


class BeslissingInvoer(BaseModel):
    type: BeslissingType
    review_reason: ReviewReason | None = None
    comment: str = ""
    wijziging: Wijziging | None = None


class StatusInvoer(BaseModel):
    """Afronden of heropenen. `gepromoveerd` staat er bewust niet bij: die toestand hoort bij het
    graaf-schrijfpad (fase 4) en is niet iets wat de jurist zelf zet."""

    status: DocumentStatus

    @model_validator(mode="after")
    def _alleen_review_toestanden(self):
        if self.status not in (DocumentStatus.in_review, DocumentStatus.geaccordeerd):
            raise ValueError("Alleen in_review of geaccordeerd kunnen hier gezet worden.")
        return self


class DocumentSamenvatting(BaseModel):
    """Eén regel in het annotatie-overzicht.

    Draagt bewust meer dan naam + aantal: het overzicht is werkvoorraad, dus het moet zonder een
    tweede call kunnen tonen wat er nog te beoordelen is, waar aandacht op staat en hoe de
    JAS-verdeling eruitziet (de kleurstrip). De telling komt uit dezelfde `tel_elementen` als de
    export.
    """

    slug: str
    bwbId: str
    artikel: str
    lid: str = ""
    citeertitel: str = ""        # weergavenaam, met terugval op werkgebied/bwbId
    werkgebied: str = ""
    status: DocumentStatus
    aantal_elementen: int
    te_beoordelen: int = 0
    per_aandacht: dict[str, int] = {}
    per_klasse: dict[str, int] = {}
    laatste_model: str = ""      # leeg = geen agent-ronde geregistreerd (of alleen eigen werk)
    updated: datetime | None = None
