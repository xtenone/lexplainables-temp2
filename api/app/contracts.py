"""Pydantic-contracten — 1-op-1 met de schema's uit references/review-checkpoints.md.

Deze modellen zijn de waarheid voor (de)serialisatie en validatie van de artefacten op disk.
De mechanische JAS-controles zitten in validation.py (hergebruik van de skill-scripts).

De analyse-eenheid is het **werkgebied** (kennisdomein) met **meerdere bronnen**. Activiteit 2
levert per bron markeringen/verwijzingen (geaggregeerd in `Analyse2.bronnen`); activiteit 3 is
werkgebied-breed: één gedeelde begrippenlijst + afleidingsregels (`Analyse3`). Id's zijn
werkgebied-breed uniek; elke markering/verwijzing draagt daarnaast een `bron_id`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Werkgebied + bron (gedeeld) ----------------------------------------------

class Werkgebied(BaseModel):
    """Het werkgebied (kennisdomein) — de afbakening waarbinnen de analyse plaatsvindt."""

    naam: str = ""
    hoofdvraag: str = ""
    omschrijving: str = ""
    scoping: str = ""   # stap 1: overwogen hoofdstukken/artikelen, in/uit-scope + reden


class Vindplaats(BaseModel):
    """Absolute, cross-bron vindplaats: welke bron + (optioneel) welk lid."""

    bron_id: str = ""
    lid: str = ""


class BronRef(BaseModel):
    """Lichte bron-index (bron_id → leesbaar label) zodat act-3 zelfstandig leesbaar is.

    Activiteit 3 draagt geen volledige bronnen, maar wel deze index, zodat de review-viewer
    en de validatie een `vindplaatsen.bron_id` naar een leesbaar label kunnen herleiden.
    """

    bron_id: str = ""
    label: str = ""
    bwbId: str = ""
    artikel: str = ""
    lid: str | None = None


# --- Activiteit 2 -------------------------------------------------------------

class Lid(BaseModel):
    lid: str
    tekst: str = ""
    bronreferentie: str = ""


class Markering(BaseModel):
    id: str
    bron_id: str = ""      # werkgebied-breed unieke id's; bron_id maakt de bron herleidbaar
    formulering: str = ""
    klasse: str = ""
    vindplaats: str = ""   # lid-relatief binnen de bron (bv. "lid 2")
    toelichting: str = ""
    twijfel: str = ""


class VerwijzingDoel(BaseModel):
    label: str = ""
    target: str = ""   # ruwe JCI/BWB-verwijzing (opaque), indien bekend
    bwbId: str = ""


class Verwijzing(BaseModel):
    """Eén uitgaande verwijzing van een bron — zie references/verwijzingen-volgen.md.

    Aparte as náást de markeringen (uitgaande pointers). `volgen` is de fetch-afweging:
    de orchestrator haalt alleen te-volgen verwijzingen daadwerkelijk op (begrensd).
    """

    id: str
    bron_id: str = ""
    bron_lid: str = ""
    soort: str = ""        # intref | extref | natuurlijk
    functie: str = ""      # definitie | schakel | delegatie | intra-artikel | informatief
    doel: VerwijzingDoel = Field(default_factory=VerwijzingDoel)
    status: str = ""       # opgehaald | gevolgd | gesignaleerd | buiten-scope-diepte
    betekenis: str = ""
    volgen: bool = False    # of de orchestrator de verwezen tekst moet ophalen


class Bron(BaseModel):
    """Eén bron in het werkgebied: een (bwbId, artikel, lid?)-eenheid met haar act-2-uitkomst."""

    bron_id: str
    label: str = ""        # leesbaar, bv. "Zvw art. 43 lid 2"
    wet: str = ""
    bwbId: str = ""
    artikel: str = ""
    lid: str | None = None
    versiedatum: str = ""
    bronreferentie: str = ""
    type: str = ""
    pad: str = ""
    reikwijdte: str = ""
    geraadpleegde: str = ""
    leden: list[Lid] = Field(default_factory=list)
    markeringen: list[Markering] = Field(default_factory=list)
    verwijzingen: list[Verwijzing] = Field(default_factory=list)
    samenhang: str = ""


class Analyse2(BaseModel):
    werkgebied: Werkgebied = Field(default_factory=Werkgebied)
    analysefocus: str = ""
    bronnen: list[Bron] = Field(default_factory=list)


# --- Activiteit 3 -------------------------------------------------------------

class BegripRelatie(BaseModel):
    """Gestructureerd kenmerk/relatie van een begrip (methode: eigenschappen en relaties)."""

    soort: str = ""            # relatie | kenmerk
    beschrijving: str = ""
    doel_begrip: str | None = None   # begrip-id bij soort=relatie, None bij soort=kenmerk


class BegripHerkomst(BaseModel):
    """Herkomst t.o.v. een aangeleverde begrippenlijst (suggestief hergebruik)."""

    status: str = "nieuw"      # hergebruikt | aangepast | nieuw
    aangeleverd_id: str = ""   # id in de aangeleverde lijst (ab1..), verplicht bij hergebruikt/aangepast
    motivatie: str = ""        # verplicht bij aangepast: waarom is afgeweken


class Begrip(BaseModel):
    id: str
    naam: str = ""                                         # de voorkeursterm (uniek per werkgebied)
    synoniemen: list[str] = Field(default_factory=list)   # alternatieve termen voor hetzelfde begrip
    klasse: str = ""
    definitie: str = ""
    is_interpretatie: bool = False   # true = (deels) eigen werkdefinitie i.p.v. letterlijke brondefinitie
    grondformulering: str = ""                            # letterlijke wetformulering (homoniem-herleiding)
    voorbeeld: str = ""
    kenmerken: str = ""              # vrije toelichting; de structuur staat in `relaties`
    relaties: list[BegripRelatie] = Field(default_factory=list)
    vindplaatsen: list[Vindplaats] = Field(default_factory=list)
    markering_ids: list[str] = Field(default_factory=list)  # act-2-markeringen waarop het begrip berust
    verwijst_naar_begrippen: list[str] = Field(default_factory=list)  # begrip-id's in de omschrijving
    bron_verwijzing: str = ""   # id van de verwijzing waarop het begrip steunt (bv. brondefinitie)
    herkomst: BegripHerkomst | None = None   # alleen relevant bij een aangeleverde begrippenlijst
    twijfel: str = ""


class RegelUitvoer(BaseModel):
    """Wat de regel afleidt — een begrip (methode: begrippen zijn de bouwstenen van regels)."""

    begrip_id: str = ""
    toelichting: str = ""


class RegelInvoer(BaseModel):
    begrip_id: str = ""
    toelichting: str = ""


class RegelParameter(BaseModel):
    """Vaste waarde in een regel; `waarde` leeg = staat in een (nog niet geanalyseerde) delegatie."""

    begrip_id: str = ""
    waarde: str = ""
    eenheid: str = ""
    geldigheid: str = ""
    vindplaats: Vindplaats = Field(default_factory=Vindplaats)
    toelichting: str = ""


class RegelVoorwaarde(BaseModel):
    """Conditie in tekst; `verbinding` is de koppeling met de vórige voorwaarde (EN/OF, leeg=eerste)."""

    tekst: str = ""
    begrip_ids: list[str] = Field(default_factory=list)
    verbinding: str = ""       # EN | OF | "" — negatie hoort in de tekst zelf


class Afleidingsregel(BaseModel):
    id: str
    naam: str = ""
    type: str = ""
    uitvoer: RegelUitvoer = Field(default_factory=RegelUitvoer)   # begrip_id is verplicht (validatie)
    invoer: list[RegelInvoer] = Field(default_factory=list)
    parameters: list[RegelParameter] = Field(default_factory=list)
    voorwaarden: list[RegelVoorwaarde] = Field(default_factory=list)
    toelichting: str = ""
    vindplaatsen: list[Vindplaats] = Field(default_factory=list)
    markering_ids: list[str] = Field(default_factory=list)  # Afleidingsregel-markering(en) uit act 2
    twijfel: str = ""


class Analyse3(BaseModel):
    werkgebied: Werkgebied = Field(default_factory=Werkgebied)
    bronnen: list[BronRef] = Field(default_factory=list)   # lichte index voor vindplaats-labels
    begrippen: list[Begrip] = Field(default_factory=list)
    afleidingsregels: list[Afleidingsregel] = Field(default_factory=list)
    validatiepunten: list[str] = Field(default_factory=list)


# --- Feedback (door de API geschreven in wacht-op-review-*) -------------------

class Feedback(BaseModel):
    # "akkoord-afronden" = akkoord op activiteit 2 én de analyse daar afronden (geen act 3);
    # de keuze is daarmee auditeerbaar in de rondes-tabel. Alleen geldig op activiteit "2",
    # zonder opmerkingen (wie nog wijzigingen heeft, rondt eerst een nieuwe ronde af).
    status: Literal["akkoord", "wijzigingen", "akkoord-afronden"]
    activiteit: Literal["2", "3", "rs-gegevens", "rs-regels"]
    items: dict[str, str] = Field(default_factory=dict)
    algemeen: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def _valideer_afronden(self) -> "Feedback":
        if self.status == "akkoord-afronden":
            if self.activiteit != "2":
                raise ValueError("akkoord-afronden kan alleen op activiteit 2")
            if self.items or self.algemeen.strip():
                raise ValueError("akkoord-afronden kan niet samen met opmerkingen")
        return self

    @field_validator("items")
    @classmethod
    def _begrens_items(cls, v: dict[str, str]) -> dict[str, str]:
        # Voorkom ongebonden payloads (opslag-/prompt-kosten): cap aantal en lengte per item.
        if len(v) > 200:
            raise ValueError("te veel feedback-items (max 200)")
        for tekst in v.values():
            if len(tekst) > 2000:
                raise ValueError("feedback-item is te lang (max 2000 tekens)")
        return v

    def is_akkoord_zonder_opmerkingen(self) -> bool:
        return self.status == "akkoord" and not self.items and not self.algemeen.strip()


# --- API-requests -------------------------------------------------------------

class BronInput(BaseModel):
    """Eén bron-keuze bij het aanmaken van een werkgebied-analyse."""

    bwbId: str | None = Field(default=None, max_length=64)
    artikel: str = Field(min_length=1, max_length=32)
    lid: str | None = Field(default=None, max_length=16)


class BegripInvoer(BaseModel):
    """Eén begrip uit een aangeleverde (bestaande) begrippenlijst — suggestieve invoer voor act 3."""

    id: str = Field(default="", max_length=32)          # bij ontbreken genummerd: ab1..abN
    naam: str = Field(min_length=1, max_length=200)
    synoniemen: list[str] = Field(default_factory=list, max_length=20)
    definitie: str = Field(default="", max_length=2000)
    klasse: str = Field(default="", max_length=64)
    bron: str = Field(default="", max_length=200)       # herkomst van de lijst (bv. begrippenkader X)
    toelichting: str = Field(default="", max_length=1000)

    @field_validator("synoniemen")
    @classmethod
    def _begrens_synoniemen(cls, v: list[str]) -> list[str]:
        for s in v:
            if len(s) > 200:
                raise ValueError("synoniem is te lang (max 200 tekens)")
        return v


class StartRequest(BaseModel):
    bronnen: list[BronInput] = Field(min_length=1, max_length=50)
    naam: str = Field(default="", max_length=200)           # werkgebied-naam
    omschrijving: str = Field(default="", max_length=2000)
    analysefocus: str | None = Field(default=None, max_length=2000)  # hoofdvraag
    # Bestaande begrippenlijst (optioneel, suggestief): act 3 hergebruikt waar de betekenis past
    # en registreert per begrip de herkomst (hergebruikt/aangepast/nieuw).
    begrippenlijst: list[BegripInvoer] | None = Field(default=None, max_length=300)
    review: bool = True
    model_profile: str | None = Field(default=None, max_length=64)


# --- Job-state ----------------------------------------------------------------

class JobState(str, Enum):
    queued = "queued"
    act2_runt = "act2-runt"
    wacht_review_act2 = "wacht-op-review-act2"
    act3_runt = "act3-runt"
    wacht_review_act3 = "wacht-op-review-act3"
    bouwt = "bouwt"
    klaar = "klaar"
    fout = "fout"
    # RegelSpraak — een on-demand vervolgfase op een afgeronde (`klaar`) analyse: eerst
    # GegevensSpraak (objectmodel), dan de RegelSpraak-regels, elk met een eigen review-checkpoint.
    rs_gegevens_runt = "rs-gegevens-runt"
    wacht_review_rs_gegevens = "wacht-op-review-rs-gegevens"
    rs_regels_runt = "rs-regels-runt"
    wacht_review_rs_regels = "wacht-op-review-rs-regels"
    rs_bouwt = "rs-bouwt"
    rs_klaar = "rs-klaar"


RUNNING_STATES = {
    JobState.act2_runt, JobState.act3_runt, JobState.bouwt,
    JobState.rs_gegevens_runt, JobState.rs_regels_runt, JobState.rs_bouwt,
}
REVIEW_STATES = {
    JobState.wacht_review_act2, JobState.wacht_review_act3,
    JobState.wacht_review_rs_gegevens, JobState.wacht_review_rs_regels,
}
# rs_klaar is terminaal: de regelspraak-fase is af. (De analyse zelf bereikte daarvóór `klaar`.)
TERMINAL_STATES = {JobState.klaar, JobState.fout, JobState.rs_klaar}

# De RegelSpraak-vervolgfase draait on-demand op een al-afgeronde (`klaar`) analyse en is geen
# nieuwe analyse-run. Deze states tellen daarom NIET mee in het max-actieve-jobs-quotum.
RS_FASE_STATES = {
    JobState.rs_gegevens_runt, JobState.wacht_review_rs_gegevens,
    JobState.rs_regels_runt, JobState.wacht_review_rs_regels, JobState.rs_bouwt,
}
# States die niet meetellen als "lopende analyse" voor het quotum: terminaal óf rs-vervolgfase.
QUOTA_VRIJE_STATES = TERMINAL_STATES | RS_FASE_STATES

# De activiteit-codes die in de rondes-tabel/provenance/current_activiteit voorkomen.
ACTIVITEIT_CODES = ("2", "3", "rs-gegevens", "rs-regels")


class FoutKlasse(str, Enum):
    mcp = "mcp"
    llm = "llm"
    validatie = "validatie"
    intern = "intern"
    quota = "quota"


class JobFout(BaseModel):
    stap: str
    ronde: int | None = None
    klasse: FoutKlasse
    bericht: str


class RondeProvenance(BaseModel):
    """Audit per gegenereerde ronde (reproduceerbaarheid)."""

    activiteit: Literal["2", "3", "rs-gegevens", "rs-regels"]
    ronde: int
    model: str = ""
    provider: str = ""
    output_strategie: str = ""
    referentie_hash: str = ""
    prompt_hash: str = ""
    mcp_bwbid: str = ""
    mcp_versiedatum: str = ""
    mcp_bronreferentie: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    # Prompt-cache-telemetrie (0 bij oudere rondes of als caching uit staat / de provider niet cachet).
    cache_read_in: int = 0
    cache_write_in: int = 0
    tijdstip: str = Field(default_factory=_now)


class Job(BaseModel):
    id: str
    state: JobState = JobState.queued
    naam: str = ""
    omschrijving: str = ""
    bronnen: list[BronInput] = Field(default_factory=list)
    review: bool = True
    model_profile: str = ""
    analysefocus: str = ""
    # Aangeleverde bestaande begrippenlijst (suggestief; zie StartRequest.begrippenlijst).
    begrippenlijst: list[BegripInvoer] = Field(default_factory=list)
    client_id: str = ""
    # Of de regelspraak-fase met review-checkpoints draait. None = nog niet gestart / erft job.review.
    regelspraak_review: bool | None = None
    # "act2" = bewust afgerond zonder activiteit 3 (via akkoord-afronden); gaat terug naar
    # "volledig" zodra activiteit 3 alsnog on-demand geclaimd wordt.
    scope: Literal["volledig", "act2"] = "volledig"
    current_activiteit: Literal["2", "3", "rs-gegevens", "rs-regels"] | None = None
    current_ronde: int = 0
    waarschuwingen: list[str] = Field(default_factory=list)
    error: JobFout | None = None
    provenance: list[RondeProvenance] = Field(default_factory=list)
    created: str = Field(default_factory=_now)
    updated: str = Field(default_factory=_now)

    def touch(self) -> None:
        self.updated = _now()


# --- API-responses (getypeerde contracten → ingevulde OpenAPI/Swagger) --------

class CreateAccepted(BaseModel):
    id: str
    naam: str = ""
    state: JobState


class JobSummary(BaseModel):
    id: str
    naam: str = ""
    state: JobState
    bronnen: list[BronInput] = Field(default_factory=list)
    updated: str = ""
    # Voor de eerste (SSR-)render van het live dashboard, zodat de kaart meteen compleet is i.p.v.
    # pas na de eerste SSE-tick. Daarna verrijkt de aggregate-SSE deze velden live.
    current_fase: str | None = None
    model_profile: str = ""
    scope: Literal["volledig", "act2"] = "volledig"
    tokens_in: int = 0
    tokens_out: int = 0


class FeedbackAccepted(BaseModel):
    id: str
    state: JobState
    ronde: int


class Rapport(BaseModel):
    """Het werkgebied-analyserapport — de primaire bron, gepresenteerd via de HTML-viewer/Markdown."""

    model_config = {"extra": "allow"}

    werkgebied: dict = Field(default_factory=dict)   # naam, hoofdvraag, omschrijving, scoping, analysefocus
    bronnen: list = Field(default_factory=list)      # per bron: metadata + leden/markeringen/verwijzingen/samenhang
    begrippen: list = Field(default_factory=list)
    afleidingsregels: list = Field(default_factory=list)
    validatiepunten: list = Field(default_factory=list)
    reviewlog: dict = Field(default_factory=dict)
    aandachtspunten: str = ""


class RegelspraakStart(BaseModel):
    """Optionele body bij het starten van de regelspraak-fase. review=None erft `Job.review`."""

    review: bool | None = None


class RegelspraakModel(BaseModel):
    """Het regelspraak-model — GegevensSpraak (objectmodel) + RegelSpraak-regels, met herkomst
    naar de wetsanalyse-begrippen/-regels. Eigen artefact náást het rapport (1-op-1 met de
    regelspraak-skill `model.json`)."""

    model_config = {"extra": "allow"}

    werkgebied: dict = Field(default_factory=dict)
    gegevensspraak: dict = Field(default_factory=dict)  # objecttypen, domeinen, parameters, feittypen, …
    regels: list = Field(default_factory=list)
    reviewlog_gegevensspraak: str = ""
    reviewlog_regels: str = ""
    validatiepunten: list = Field(default_factory=list)
    reviewlog: dict = Field(default_factory=dict)
