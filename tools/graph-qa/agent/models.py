"""
Pydantic-modellen voor request/response van de graph-qa API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class BestaandElement(BaseModel):
    """Een element dat al in het annotatie-document staat, meegestuurd door de werkplek.

    De agent kan niet zelf in het document kijken (dat leeft in de api), dus de werkplek geeft door
    wat er al ligt. De Critic kan zo ook meekijken op wat de JURIST heeft gemarkeerd — als suggestie,
    nooit als wijziging.
    """

    id: str = ""
    klasse: str = ""
    tekst: str = ""
    lid: str = ""
    herkomst: str = "agent"        # agent | mens


class ChatContext(BaseModel):
    """Waar de vraag over gaat. Alleen ingevuld als de werkplek een specifieke bepaling of markering
    in beeld heeft; bij een gewone vraag blijft dit leeg."""

    slug: str = ""
    bwbId: str = ""
    artikel: str = ""
    lid: str = ""
    element_id: str = ""
    klasse: str = ""
    fragment: str = ""             # de selectie of de tekst van het element
    corpus: str = ""               # de getoonde artikeltekst
    bestaande_elementen: list[BestaandElement] = []


class AgentDoel(BaseModel):
    """De bepaling die geannoteerd moet worden, als de aanroeper die al weet.

    De werkplek kent hem vaak: een open document, een item uit de werkvoorraad, of een kandidaat die
    de jurist zojuist aanklikte. Meesturen scheelt de supervisor-call én de hele ophaal-agent, maar
    het echte winstpunt is dat de agent dan niet meer kán uitkomen bij een ándere bepaling dan de
    jurist aanwees. Zonder doel gaat de beurt de gewone weg: supervisor → ophaal-agent.
    """

    bwbId: str = ""
    artikel: str = ""
    lid: str = ""
    nummer: str = ""          # decimale bepaling (beleidsregel/circulaire), bv. "9.1"
    citeertitel: str = ""


class ChatRequest(BaseModel):
    question: str
    conversation_id: str | None = None  # stuur mee voor gespreksgeheugen
    doel: AgentDoel | None = None
    # "advies" = een vraag bij een bestaande annotatie. De supervisor kiest dan niet zelf, maar
    # routeert hard naar de antwoord-worker: zo kan een adviesvraag structureel geen annotatie
    # wijzigen (die route emit simpelweg geen doel/element-events).
    modus: Literal["auto", "advies"] = "auto"
    context: ChatContext | None = None


class RunStart(BaseModel):
    """Wat een client van een run weet zónder mee te kijken.

    `vraag` zit erbij omdat een tabblad dat halverwege aanhaakt anders tokens uit het niets krijgt:
    de vraag hoort bij de run, niet bij het tabblad dat hem startte. `volgende_seq` en `weggevallen`
    zeggen waar de eventlog staat, zodat aanhaken vanaf het juiste punt kan.
    """

    run_id: str
    conversation_id: str = ""
    vraag: str = ""
    status: str = "loopt"          # loopt | klaar | gestopt | mislukt
    volgende_seq: int = 0
    weggevallen: int = 0


class Source(BaseModel):
    label: str
    uri: str
    # Herkomst-velden (additief; de frontend-BFF leest alleen label + uri).
    iri: str | None = None
    jci: str | None = None
    origin_tool: str | None = None


# SSE-events
class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    content: str


class SourcesEvent(BaseModel):
    type: Literal["sources"] = "sources"
    sources: list[Source]


class GroundingEvent(BaseModel):
    """De uitkomst van de brongetrouwheidstoets op het antwoord.

    `niveau` is fijner dan `grounded` en is de waarde om te tonen: "onbepaald" betekent dat het
    antwoord geen enkele vindplaats of citaat noemde en er dus niets te controleren viel. Dat als
    "gegrond" presenteren zou schijnzekerheid zijn.
    """

    type: Literal["grounding"] = "grounding"
    grounded: bool
    cited: int = 0
    unsupported: list[str] = []
    # Als citaat gepresenteerde tekst die niet letterlijk in de opgehaalde tekst staat.
    niet_letterlijk: list[str] = []
    niveau: Literal["gegrond", "onbepaald", "ongegrond"] = "gegrond"


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str


# --- Annotatie (JAS) ---------------------------------------------------------

class AnnotatieAlternatief(BaseModel):
    """Een kandidaat-klasse bij twijfel, met korte motivatie (disambiguatie)."""

    klasse: str
    motivatie: str = ""


class CriticRonde(BaseModel):
    """Wat de Critic in één pas van dit element vond, en wat hij ermee wilde.

    Spiegelt `CriticRonde` in `api/app/annotatie_contracts.py`; de api merget ze op `ronde` en vult
    `tijd` zelf. Deze regels zijn drie dingen tegelijk: het geheugen van de Critic in een volgende
    ronde, het spoor dat de jurist op de kaart terugziet, en de reden dat de lus kan zien of een punt
    al eens is gemaakt.
    """

    ronde: int
    aandacht: str = ""                 # groen | geel | rood
    motivatie: str = ""
    actie: str = "behoud"              # behoud | vervang | verwijder
    # Is de instructie ook uitgevoerd? De patcher (`annotatie.pas_critic_toe`) zet dit. Zonder dit
    # verschilt "de Critic vroeg erom" niet van "het is ook gebeurd" — en dat verschil moet een
    # auditspoor kunnen laten zien.
    toegepast: bool = False
    voorstel_klasse: str = ""
    voorstel_tekst: str = ""


class AgentRun(BaseModel):
    """De herkomst van één annotatiebeurt: wélk model de voorstellen maakte.

    Reist als `run`-event mee naar de werkplek, die het bij de api vastlegt. Zonder deze gegevens
    is achteraf niet te zeggen waar een markering vandaan komt — precies wat een export moet dragen
    en wat de latere promotie naar de graaf als provenance nodig heeft.
    """

    model: str = ""
    provider: str = ""
    agent_versie: str = ""
    critic_rondes: int = 0
    stop_reden: str = ""
    tijd: datetime | None = None


class AnnotatieVoorstel(BaseModel):
    """Eén door de agent voorgesteld JAS-annotatie-element voor een artikel.

    `tekst` is een letterlijk fragment uit de artikeltekst; `grounded`/`vindplaats` worden
    server-side ingevuld door de brongetrouwheid-check (nooit door het model).
    """

    # Stabiel id, hier toegekend (niet door het model). De Critic verwijst ernaar en de api matcht
    # erop bij een volgende ronde; op positie koppelen breekt zodra een herziening iets toevoegt.
    id: str = ""
    klasse: str
    tekst: str
    lid: str = ""
    toelichting: str = ""
    alternatieven: list[AnnotatieAlternatief] = []
    grounded: bool = False
    vindplaats: str = ""               # bwbId/artikel/lid/jci-notatie
    aandacht: str = ""                 # "" | groen | geel | rood — gezet door de Critic-node
    critic: str = ""                   # korte Critic-motivatie bij het aandacht-niveau
    critic_rondes: list[CriticRonde] = []   # het heen-en-weer per ronde; leeg tot de eerste Critic-pas


class CriticOordeel(BaseModel):
    """Wat de Critic van één voorstel vindt, inclusief wat de annoteerder ermee moet doen.

    Zonder `actie`/`voorstel_*` is een herzieningsronde onmogelijk: dan weet de annoteerder wél dat
    er iets mis is, maar niet wat.
    """

    aandacht: str = ""                 # groen | geel | rood
    motivatie: str = ""
    actie: str = "behoud"              # behoud | vervang | verwijder
    voorstel_klasse: str = ""
    voorstel_tekst: str = ""


class OntbrekendItem(BaseModel):
    """Een door de Critic vermoed ontbrekend element: een JAS-klasse die waarschijnlijk óók in de tekst
    zit maar niet is gemarkeerd. `tekst` is optioneel — staat er een letterlijk fragment bij, dan kan
    een herzieningsronde het element daadwerkelijk toevoegen in plaats van alleen een klasse te roepen."""

    klasse: str
    reden: str = ""
    tekst: str = ""


class VerworpenFragment(BaseModel):
    """Een voorstel dat de grondingscheck niet haalde.

    Werd eerder alleen geteld en weggegooid. Juist deze informatie laat het model zichzelf
    corrigeren: "dit citaat staat niet letterlijk in de tekst" is een aanwijzing, geen fout."""

    klasse: str
    tekst: str
    reden: str                         # ongeldige_klasse | niet_letterlijk


# --- Artikeltekst uit de graaf (workbench-documentpaneel) ---------------------

class LidTekst(BaseModel):
    lid: str = ""
    tekst: str = ""


class ArtikelResult(BaseModel):
    """Artikeltekst uit de graaf voor het workbench-documentpaneel (weergave == annotatie-corpus)."""

    bwbId: str
    artikel: str
    citeertitel: str = ""
    opschrift: str = ""
    leden_teksten: list[LidTekst] = []
