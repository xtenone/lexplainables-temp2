"""
De wetsanalyse-workbench-resource (gemount onder /v1/annotatie).

Vers annotatie-domein: documenten per bron, per element een human-decision (approve/edit/reject/
comment/heropen) en een append-only audit trail. Een beoordeeld element (`human_approved`/`rejected`)
en een afgerond document (`geaccordeerd`) zijn op slot: wijzigen kan pas na een expliciete
heropening, en die staat zelf in het spoor. **Per-gebruiker gescopet** via de vertrouwde `X-User-Id`
(`huidige_userid`, zoals de gesprekken) — 404 (niet 403) bij andermans document, zodat het bestaan niet
lekt; de bearer-`client_id` blijft als herkomst in de audit. JAS-klassen worden gevalideerd tegen
`validation.GELDIGE_JAS_KLASSEN`.

POST   /v1/annotatie/documenten                                  — maak document
GET    /v1/annotatie/documenten?limit=&offset=                   — eigen documenten (samenvatting)
GET    /v1/annotatie/documenten/{slug}                           — volledig document
DELETE /v1/annotatie/documenten/{slug}                           — verwijder eigen document
PUT    /v1/annotatie/documenten/{slug}/elementen                 — uitkomst van een agent-ronde (merge)
POST   /v1/annotatie/documenten/{slug}/elementen                 — eigen markering toevoegen (jurist)
DELETE /v1/annotatie/documenten/{slug}/elementen/{id}            — eigen markering verwijderen
POST   /v1/annotatie/documenten/{slug}/elementen/{id}/beslissing — human-decision (incl. heropen)
POST   /v1/annotatie/documenten/{slug}/status                    — afronden / heropenen
GET    /v1/annotatie/documenten/{slug}/audit                     — append-only tijdlijn
POST   /v1/annotatie/documenten/{slug}/export?formaat=…          — export (pdf|csv|json)
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel

from ..annotatie_contracts import (
    VERGRENDELDE_LIFECYCLES,
    AgentRun,
    AnnotatieDocument, AnnotatieElement, AuditRecord, Beslissing, BeslissingInvoer, BeslissingType,
    DocumentStatus,
    CriticSuggestie, DocumentCreate, DocumentSamenvatting, ElementInvoer, ElementenInvoer,
    Lifecycle,
    MensElementInvoer,
    ReviewReason,
    StatusInvoer,
)
from ..annotatie_export import (
    FORMATEN, LidTekst, bestandsnaam, bouw_export, serialiseer, tel_elementen, weergavenaam,
)
from ..annotatie_store import CONFLICT, GEEN_ELEMENT, AnnotatieStore, etag_van
from ..auth import require_client
from ..db import utcnow
from ..deps import get_annotatie_store
from ..validation import GELDIGE_JAS_KLASSEN
from .auth import actieve_userid

router = APIRouter(prefix="/annotatie", tags=["annotatie"])

# Velden die een agent-ronde inhoudelijk mag bijwerken op een niet-bevroren element.
_INHOUD_VELDEN = ("klasse", "tekst", "lid", "toelichting", "vindplaats")


#: Sentinel: het document (of het element) staat op slot. Komt als 409 terug bij de client.
AFGEROND = object()
VERGRENDELD = object()
NIET_VERGRENDELD = object()


def _afgerond(doc: AnnotatieDocument) -> bool:
    """Een afgerond document is bevroren — voor de jurist én voor een nieuwe agent-ronde.

    Zonder deze grens betekende `geaccordeerd` niets: er kon daarna nog van alles bij, af en overheen.
    Heropenen is één klik (`POST .../status`), dus dit is een drempel en geen doodlopende weg.
    """
    return doc.status is DocumentStatus.geaccordeerd


def _sleutel(tekst: str, lid: str) -> tuple[str, str]:
    """Terugvalsleutel voor clients die (nog) geen element-id meesturen: genormaliseerde tekst + lid.
    Bewust ZONDER klasse — een herziening mag juist de klasse veranderen en moet dan hetzelfde
    element treffen, niet een duplicaat maken."""
    return (" ".join(tekst.split()).casefold(), lid or "")


#: Welke reden hoort bij een edit van precies dít veld? Meer dan één veld tegelijk → `anders`.
_REDEN_PER_VELD: dict[str, ReviewReason] = {
    "tekst": ReviewReason.tekst,
    "klasse": ReviewReason.verkeerde_klasse,
    "toelichting": ReviewReason.interpretatie,
}


def _reden_uit_diff(diff: dict) -> ReviewReason:
    """De `review_reason` bij een edit, afgeleid uit wát er veranderde.

    Die afleiding stond in de browser (`frontend/lib/annotatie.ts:redenVoorWijziging`) terwijl de
    server dezelfde diff toch al berekent. De reden in het auditspoor was daarmee een waarde die de
    server aannam maar nooit kon controleren — in een systeem dat om herleidbaarheid draait hoort
    hij te worden vastgesteld waar het bewijs ligt.

    Alleen `lid`, of meer dan één veld tegelijk, valt onder `anders`: geen van de vaste redenen
    dekt dat. Een lege diff komt hier niet: die wordt eerder als no-op afgevangen.
    Bij een REJECT blijft de reden een vraag aan de mens — die informatie staat niet in een diff.
    """
    if len(diff) != 1:
        return ReviewReason.anders
    return _REDEN_PER_VELD.get(next(iter(diff)), ReviewReason.anders)


def _is_bevroren(el: AnnotatieElement) -> bool:
    """Mag de agent dit element nog inhoudelijk wijzigen?

    Nee zodra de jurist eraan te pas kwam: een eigen element of een element waarover al besloten is.
    Dat is de kern van 'de mens heeft het laatste woord' — zonder deze regel wist een volgende
    agent-ronde stilzwijgend een goedkeuring of een handmatige correctie.
    """
    return el.herkomst == "mens" or bool(el.beslissingen)


def _uit_invoer(e: ElementInvoer, element_id: str, run: AgentRun | None) -> AnnotatieElement:
    """Nieuw agent-element uit een voorstel. Heeft de Critic een aandacht-niveau gezet, dan is het al
    door de Critic gezien → lifecycle `critic_checked`, anders `voorgesteld`.

    `run` legt vast wélk model dit voorstel maakte; ontbreekt hij (client van vóór de registratie),
    dan blijft het veld leeg in plaats van dat er een model wordt aangenomen."""
    return AnnotatieElement(
        id=element_id, klasse=e.klasse, tekst=e.tekst, lid=e.lid,
        toelichting=e.toelichting, vindplaats=e.vindplaats,
        herkomst="agent",
        lifecycle=Lifecycle.critic_checked if e.aandacht is not None else Lifecycle.voorgesteld,
        alternatieven=e.alternatieven, aandacht=e.aandacht, critic=e.critic,
        critic_rondes=list(e.critic_rondes), anker=e.anker,
        geproduceerd_door=run,
    )


def _voeg_critic_toe(el: AnnotatieElement, e: ElementInvoer) -> bool:
    """Zet het Critic-oordeel op een bestaand element. Geeft terug of er iets veranderde.

    Mag ook op een bevroren element: dat de Critic er later nog iets van vond is informatie die de
    jurist wil zien — het raakt zijn besluit niet.
    """
    veranderd = False
    if e.aandacht is not None and (el.aandacht != e.aandacht or el.critic != e.critic):
        el.aandacht, el.critic = e.aandacht, e.critic
        veranderd = True
    bekend = {r.ronde for r in el.critic_rondes}
    for ronde in e.critic_rondes:
        if ronde.ronde not in bekend:
            el.critic_rondes.append(ronde)
            veranderd = True
    return veranderd


async def _document_or_404(store: AnnotatieStore, slug: str, user_id: str) -> AnnotatieDocument:
    """Laadt het document en dwingt eigenaarschap af. 404 (niet 403) bij mismatch — lekt niet.
    Per-gebruiker gescopet: de eigenaar is de ingelogde gebruiker (`user_id`), niet de bearer-client."""
    doc = await store.laad_document(slug)
    if doc is None or doc.user_id != user_id:
        raise HTTPException(status_code=404, detail=f"Onbekend annotatie-document: {slug}")
    return doc


@router.post("/documenten", status_code=status.HTTP_201_CREATED, response_model=AnnotatieDocument)
async def maak_document(
    req: DocumentCreate,
    user_id: str = Depends(actieve_userid),
    client_id: str = Depends(require_client),
    store: AnnotatieStore = Depends(get_annotatie_store),
):
    slug = uuid.uuid4().hex[:16]
    doc = AnnotatieDocument(
        slug=slug, user_id=user_id, client_id=client_id,
        citeertitel=req.citeertitel, werkgebied=req.werkgebied,
        bwbId=req.bwbId, artikel=req.artikel, lid=req.lid or "",
    )
    await store.maak_document(doc)
    await store.schrijf_audit(
        slug, client_id, user_id, "document-aangemaakt",
        detail={"bwbId": req.bwbId, "artikel": req.artikel, "lid": req.lid or "",
                "citeertitel": req.citeertitel},
    )
    return await store.laad_document(slug)


@router.get("/documenten", response_model=list[DocumentSamenvatting])
async def lijst_documenten(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(actieve_userid),
    store: AnnotatieStore = Depends(get_annotatie_store),
):
    docs = await store.lijst_documenten(user_id, limit, offset)
    uit: list[DocumentSamenvatting] = []
    for d in docs:
        telling = tel_elementen(d.elementen)
        # Het laatst gebruikte model: de runs staan op volgorde van uitvoering, dus de laatste met
        # een modelnaam is de actuele. Leeg blijft leeg — nooit een model aannemen.
        laatste = next((r.model for r in reversed(d.runs) if r.model), "")
        uit.append(DocumentSamenvatting(
            slug=d.slug, bwbId=d.bwbId, artikel=d.artikel, lid=d.lid,
            citeertitel=weergavenaam(d), werkgebied=d.werkgebied,
            status=d.status, aantal_elementen=len(d.elementen),
            te_beoordelen=telling.te_beoordelen,
            per_aandacht=telling.per_aandacht, per_klasse=telling.per_klasse,
            laatste_model=laatste, updated=d.updated,
        ))
    return uit


@router.get("/documenten/{slug}", response_model=AnnotatieDocument)
async def haal_document(
    slug: str,
    user_id: str = Depends(actieve_userid),
    store: AnnotatieStore = Depends(get_annotatie_store),
):
    return await _document_or_404(store, slug, user_id)


@router.delete("/documenten/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def verwijder_document(
    slug: str,
    user_id: str = Depends(actieve_userid),
    store: AnnotatieStore = Depends(get_annotatie_store),
):
    await _document_or_404(store, slug, user_id)
    await store.verwijder_document(slug)


@router.put("/documenten/{slug}/elementen", response_model=AnnotatieDocument)
async def zet_elementen(
    slug: str,
    req: ElementenInvoer,
    response: Response,
    user_id: str = Depends(actieve_userid),
    client_id: str = Depends(require_client),
    store: AnnotatieStore = Depends(get_annotatie_store),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    """De uitkomst van één agent-ronde SAMENVOEGEN met wat er al staat.

    Bewust een merge en geen vervanging: de agent kan meerdere rondes draaien (annoteerder ⇄ Critic)
    en de jurist werkt in hetzelfde document. Vervangen wiste eerder alle beslissingen, levenscyclus
    en element-id's — met een auditlog dat daarna naar niet-bestaande id's verwees.

    Matcht op `id`, met de genormaliseerde tekst als terugval voor clients die nog geen id sturen.
    Elementen waar de jurist aan te pas kwam zijn bevroren (§`_is_bevroren`); die krijgen hooguit een
    nieuw Critic-oordeel. Ongeldige klasse of leeg fragment wordt verworpen (stil, met een teller in
    de audit — de agent grondt zelf al en dit is het vangnet).
    """
    # Twee soorten "verworpen", één teller: wat het schema niet haalde (afgevangen door
    # `ElementenInvoer._weiger_per_element`, anders was dit een 422 en landde er níéts) en wat de
    # merge hieronder afwijst op klasse of leeg fragment. Voor de jurist is dat hetzelfde feit.
    verworpen = len(req.geweigerd)
    regels: list[tuple] = []

    def merge(doc: AnnotatieDocument):
        nonlocal verworpen
        if _afgerond(doc):
            return AFGEROND
        op_id = {el.id: el for el in doc.elementen}
        # Terugvalindex: alleen agent-elementen, want een mens-element mag nooit stilzwijgend door
        # een agent-voorstel worden overgenomen enkel omdat de tekst toevallig gelijk is.
        op_sleutel: dict[tuple[str, str], list[AnnotatieElement]] = {}
        for el in doc.elementen:
            if el.herkomst == "agent":
                op_sleutel.setdefault(_sleutel(el.tekst, el.lid), []).append(el)
        gezien: set[str] = set()

        for e in req.elementen:
            if e.klasse not in GELDIGE_JAS_KLASSEN or not e.tekst.strip():
                verworpen += 1
                continue

            el = op_id.get(e.id) if e.id else None
            if el is None:
                kandidaten = op_sleutel.get(_sleutel(e.tekst, e.lid)) or []
                el = next((k for k in kandidaten if k.id not in gezien), None)

            if el is None:
                nieuw = _uit_invoer(e, e.id or uuid.uuid4().hex[:12], req.run)
                doc.elementen.append(nieuw)
                op_id[nieuw.id] = nieuw
                gezien.add(nieuw.id)
                regels.append(("element-voorgesteld", nieuw.id, {
                    "ronde": req.ronde, "klasse": nieuw.klasse, "tekst": nieuw.tekst,
                    "lid": nieuw.lid, "aandacht": nieuw.aandacht.value if nieuw.aandacht else None,
                }))
                continue

            gezien.add(el.id)
            if _is_bevroren(el):
                if _voeg_critic_toe(el, e):
                    regels.append(("critic-suggestie", el.id, {
                        "ronde": req.ronde, "aandacht": e.aandacht.value if e.aandacht else None,
                        "motivatie": e.critic,
                    }))
                continue

            diff = {
                veld: {"voor": getattr(el, veld), "na": getattr(e, veld)}
                for veld in _INHOUD_VELDEN
                if getattr(e, veld) != getattr(el, veld)
            }
            for veld in diff:
                setattr(el, veld, getattr(e, veld))
            if e.alternatieven:
                el.alternatieven = e.alternatieven
            critic_bij = _voeg_critic_toe(el, e)
            if e.anker is not None:
                el.anker = e.anker
            if diff:
                el.gewijzigd_door = "agent"
                # De herziening komt van DEZE run: de herkomst schuift mee, anders wijst hij naar
                # een model dat deze inhoud niet heeft geproduceerd.
                if req.run is not None:
                    el.geproduceerd_door = req.run
                el.lifecycle = Lifecycle.critic_checked if el.aandacht is not None else Lifecycle.voorgesteld
                regels.append(("element-herzien", el.id, {"ronde": req.ronde, "diff": diff}))
            elif critic_bij:
                el.lifecycle = Lifecycle.critic_checked if el.aandacht is not None else el.lifecycle

        # Kanttekeningen bij eigen markeringen. Op een agent-element hoort een kaal oordeel gewoon
        # in `aandacht` thuis — maar een concreet voorstel uit de eindbeoordeling past daar niet in,
        # en er komt geen correctiestap meer overheen. Dat mag hier dus wél landen, zodat de jurist
        # het met één klik overneemt in plaats van het met de hand na te doen.
        for s in req.suggesties:
            el = op_id.get(s.element_id)
            if el is None:
                continue
            if el.herkomst != "mens" and not (s.voorstel_tekst or s.voorstel_klasse):
                continue
            el.critic_suggestie = CriticSuggestie(
                aandacht=s.aandacht, motivatie=s.motivatie,
                voorstel_klasse=s.voorstel_klasse, voorstel_tekst=s.voorstel_tekst,
            )
            regels.append(("critic-suggestie", el.id, {
                "ronde": req.ronde, "aandacht": s.aandacht.value if s.aandacht else None,
                "motivatie": s.motivatie,
            }))

        if req.run is not None:
            doc.runs.append(req.run)

        if req.trek_ontbrekende_in:
            behouden = []
            for el in doc.elementen:
                if el.id in gezien or _is_bevroren(el):
                    behouden.append(el)
                else:
                    regels.append(("element-ingetrokken", el.id,
                                   {"ronde": req.ronde, "klasse": el.klasse, "tekst": el.tekst}))
            doc.elementen = behouden
        return None

    uitkomst = await store.muteer_document(slug, user_id, merge, if_match=if_match)
    if uitkomst is None:
        raise HTTPException(status_code=404, detail=f"Onbekend annotatie-document: {slug}")
    if uitkomst is CONFLICT:
        raise HTTPException(status_code=412, detail="Het document is inmiddels gewijzigd.")
    if uitkomst is AFGEROND:
        raise HTTPException(status_code=409, detail="Deze annotatie is afgerond. Heropen hem om te wijzigen.")

    doc: AnnotatieDocument = uitkomst  # type: ignore[assignment]
    telling = {a: sum(1 for r in regels if r[0] == a) for a in
               ("element-voorgesteld", "element-herzien", "element-ingetrokken", "critic-suggestie")}
    await store.schrijf_auditregels(slug, client_id, user_id, [
        ("elementen-voorgesteld", None, {
            "ronde": req.ronde,
            "aangeboden": len(req.elementen) + len(req.geweigerd),
            "verworpen": verworpen,
            # Wát er sneuvelde, niet alleen hoevéél. Een teller vertelt de jurist dat er iets weg is;
            # dit vertelt hem wat, zodat hij het zelf kan markeren.
            **({"geweigerd": req.geweigerd} if req.geweigerd else {}),
            "nieuw": telling["element-voorgesteld"], "herzien": telling["element-herzien"],
            "ingetrokken": telling["element-ingetrokken"], "suggesties": telling["critic-suggestie"],
            # De onwijzigbare vastlegging van de herkomst: het document draagt de huidige staat,
            # het auditlog draagt wat er wanneer met welk model gebeurde.
            "model": req.run.model if req.run else "",
            "provider": req.run.provider if req.run else "",
            "agent_versie": req.run.agent_versie if req.run else "",
            "critic_rondes": req.run.critic_rondes if req.run else 0,
            "stop_reden": req.run.stop_reden if req.run else "",
        }),
        *regels,
    ])
    response.headers["ETag"] = etag_van(doc)
    # De aanroeper (graph-qa) leest dit en waarschuwt de jurist. Zonder dat ruilen we een luide fout
    # — een leeg document, meteen zichtbaar — in voor een stille: dertien markeringen waarvan
    # niemand weet dat het er vijftien hadden moeten zijn. Een header, want de respons is het
    # document en dat hoort niet met verwerkingsdetails te vervuilen.
    if verworpen:
        response.headers["X-Verworpen"] = str(verworpen)
    return doc


@router.post("/documenten/{slug}/elementen", status_code=status.HTTP_201_CREATED,
             response_model=AnnotatieDocument)
async def voeg_element_toe(
    slug: str,
    req: MensElementInvoer,
    user_id: str = Depends(actieve_userid),
    client_id: str = Depends(require_client),
    store: AnnotatieStore = Depends(get_annotatie_store),
):
    """Eén element dat de JURIST zelf aanmaakt (een tekstselectie in het documentpaneel).

    Apart van de PUT, want dat is "de uitkomst van een agent-ronde" en dit is iets anders: het komt
    er los bij en raakt de rest niet. `herkomst="mens"` en meteen `human_approved` — de mens hoeft
    zijn eigen markering niet nog eens goed te keuren.
    """
    if req.klasse not in GELDIGE_JAS_KLASSEN:
        raise HTTPException(status_code=422, detail=f"Onbekende JAS-klasse: {req.klasse}")
    if not req.tekst.strip():
        raise HTTPException(status_code=422, detail="Een markering heeft een tekstfragment nodig.")

    element_id = uuid.uuid4().hex[:12]

    def voeg_toe(doc: AnnotatieDocument):
        if _afgerond(doc):
            return AFGEROND
        doc.elementen.append(AnnotatieElement(
            id=element_id, klasse=req.klasse, tekst=req.tekst, lid=req.lid,
            toelichting=req.toelichting, vindplaats=req.vindplaats, anker=req.anker,
            herkomst="mens", lifecycle=Lifecycle.human_approved,
        ))
        return None

    uitkomst = await store.muteer_document(slug, user_id, voeg_toe)
    if uitkomst is None:
        raise HTTPException(status_code=404, detail=f"Onbekend annotatie-document: {slug}")
    if uitkomst is AFGEROND:
        raise HTTPException(status_code=409, detail="Deze annotatie is afgerond. Heropen hem om te wijzigen.")
    await store.schrijf_audit(
        slug, client_id, user_id, "element-toegevoegd", element_id=element_id,
        detail={"klasse": req.klasse, "tekst": req.tekst, "lid": req.lid},
    )
    return uitkomst


@router.delete("/documenten/{slug}/elementen/{element_id}", status_code=status.HTTP_204_NO_CONTENT)
async def verwijder_element(
    slug: str,
    element_id: str,
    user_id: str = Depends(actieve_userid),
    client_id: str = Depends(require_client),
    store: AnnotatieStore = Depends(get_annotatie_store),
):
    """Verwijder een EIGEN markering. Agent-elementen verdwijnen niet: die verwerp je (`reject`),
    zodat het auditspoor laat zien dát er een voorstel was en wat ermee gebeurde."""
    verwijderd: dict = {}

    def verwijder(doc: AnnotatieDocument):
        if _afgerond(doc):
            return AFGEROND
        el = next((x for x in doc.elementen if x.id == element_id), None)
        if el is None:
            return GEEN_ELEMENT
        if el.herkomst != "mens":
            return CONFLICT
        verwijderd.update({"klasse": el.klasse, "tekst": el.tekst})
        doc.elementen = [x for x in doc.elementen if x.id != element_id]
        return None

    uitkomst = await store.muteer_document(slug, user_id, verwijder)
    if uitkomst is None or uitkomst is GEEN_ELEMENT:
        raise HTTPException(status_code=404, detail="Onbekend element.")
    if uitkomst is AFGEROND:
        raise HTTPException(status_code=409, detail="Deze annotatie is afgerond. Heropen hem om te wijzigen.")
    if uitkomst is CONFLICT:
        raise HTTPException(
            status_code=409,
            detail="Alleen je eigen markeringen kun je verwijderen; verwerp een agent-voorstel.",
        )
    await store.schrijf_audit(slug, client_id, user_id, "element-verwijderd",
                              element_id=element_id, detail=verwijderd)


@router.post("/documenten/{slug}/elementen/{element_id}/beslissing", response_model=AnnotatieDocument)
async def beslis(
    slug: str,
    element_id: str,
    req: BeslissingInvoer,
    user_id: str = Depends(actieve_userid),
    client_id: str = Depends(require_client),
    store: AnnotatieStore = Depends(get_annotatie_store),
):
    # Pre-validatie die het element niet nodig heeft (faalt vóór de atomaire mutatie).
    if req.type == BeslissingType.edit:
        # `review_reason` is hier bewust NIET verplicht: de server leidt hem af uit de diff die hij
        # zelf berekent (`_reden_uit_diff`). Een meegestuurde waarde geldt hooguit als hint en
        # wordt overschreven — anders staat er een reden in het auditspoor die niemand kan toetsen.
        if req.wijziging is None:
            raise HTTPException(status_code=422, detail="wijziging is verplicht bij een edit.")
        if req.wijziging.klasse is not None and req.wijziging.klasse not in GELDIGE_JAS_KLASSEN:
            raise HTTPException(status_code=422, detail=f"Ongeldige JAS-klasse: {req.wijziging.klasse}")
    elif req.type == BeslissingType.reject:
        if req.review_reason is None:
            raise HTTPException(status_code=422, detail="review_reason is verplicht bij een reject.")

    diff_holder: dict = {}
    anker_verplaatst: dict = {}
    geen_wijziging: dict[str, bool] = {}
    reden_holder: dict[str, ReviewReason | None] = {"reden": req.review_reason}

    def toepassen(doc: AnnotatieDocument, el: AnnotatieElement):
        """Muteert het element in-place binnen de atomaire store-transactie (row-lock).

        De poortwachter staat hier en niet vóór de transactie: `lifecycle` en `status` mogen tussen
        het lezen en het schrijven niet verschoven zijn, anders glipt er alsnog een wijziging langs
        een akkoord heen.
        """
        if _afgerond(doc):
            return AFGEROND
        # Een EIGEN markering staat meteen op `human_approved` — je hoeft je eigen markering niet
        # nog eens goed te keuren. Dat is "gemaakt", niet "beoordeeld": vergrendelen zou hem bij het
        # aanmaken al op slot zetten. Het slot beschermt een review-oordeel over een agent-voorstel.
        vergrendeld = el.herkomst != "mens" and el.lifecycle in VERGRENDELDE_LIFECYCLES
        # Een opmerking plaatsen wijzigt de annotatie niet en mag dus ook op een vergrendeld element:
        # juist bij iets dat vaststaat wil je een kanttekening kunnen achterlaten.
        if vergrendeld and req.type not in (BeslissingType.heropen, BeslissingType.comment):
            return VERGRENDELD
        if req.type == BeslissingType.heropen and not vergrendeld:
            return NIET_VERGRENDELD

        diff: dict = {}
        if req.type == BeslissingType.edit:
            for veld in ("klasse", "tekst", "toelichting", "lid"):
                nieuw = getattr(req.wijziging, veld)
                if nieuw is not None and nieuw != getattr(el, veld):
                    diff[veld] = {"voor": getattr(el, veld), "na": nieuw}
                    setattr(el, veld, nieuw)
            # Het anker hoort bij de tekst en volgt hem dus: meegestuurd anker wint, geen anker bij
            # een gewijzigd fragment wist het oude. Bewust NIET in de `diff` — dat is machinerie, geen
            # inhoudelijke wijziging die de jurist in zijn reviewspoor wil terugzien.
            if "tekst" in diff:
                el.anker = req.wijziging.anker
                anker_verplaatst["ja"] = req.wijziging.anker is not None
            elif req.wijziging.anker is not None:
                el.anker = req.wijziging.anker
                anker_verplaatst["ja"] = True
            # Een edit die niets verandert is geen beslissing. Zonder deze poort schreef elke klik
            # er één, ook als de waarde al zo stond: op dev leverde één suggestie die niet zichtbaar
            # werd overgenomen zestien beslissingen op hetzelfde element, waarvan vijftien leeg.
            # Een auditspoor dat vol staat met niet-gebeurtenissen is moeilijker te lezen dan een
            # kort spoor, en dat spoor is hier het product.
            if not diff:
                geen_wijziging["ja"] = True
                return None
            el.lifecycle = Lifecycle.edited
            # NIET `herkomst` — dat blijft wie het element aanmaakte. Een edit door de jurist maakt
            # er geen mens-element van; anders is later niet meer te zien dat de agent het voorstelde.
            el.gewijzigd_door = "mens"
            el.diff = diff
            # De reden volgt uit de diff die hier net is berekend, niet uit wat de client meestuurde.
            reden_holder["reden"] = _reden_uit_diff(diff)
            # Neemt de jurist over wat de Critic voorstelde, dan is die kanttekening afgehandeld.
            # Bleef hij op "open" staan, dan bleef de kaart om een keuze vragen die al gemaakt is —
            # en dat las als "er gebeurt niets".
            sug = el.critic_suggestie
            if sug and sug.status == "open" and (
                ("tekst" in diff and diff["tekst"]["na"] == sug.voorstel_tekst)
                or ("klasse" in diff and diff["klasse"]["na"] == sug.voorstel_klasse)
            ):
                sug.status = "geaccepteerd"
        elif req.type == BeslissingType.approve:
            el.lifecycle = Lifecycle.human_approved
        elif req.type == BeslissingType.reject:
            el.lifecycle = Lifecycle.rejected
        elif req.type == BeslissingType.heropen:
            # Terug naar de stand van vóór het oordeel. Wél `critic_checked` als de Critic er al
            # naar keek — anders zou heropenen dat oordeel uit beeld poetsen en lijkt het element
            # ongezien. `diff` blijft staan: dat is het spoor van de laatste edit, geen huidige stand.
            el.lifecycle = Lifecycle.critic_checked if el.critic else Lifecycle.voorgesteld
            el.gewijzigd_door = "mens"
        # comment → geen lifecycle-wijziging
        el.beslissingen.append(Beslissing(
            type=req.type, actor=user_id, tijd=utcnow(),
            review_reason=reden_holder["reden"], comment=req.comment, wijziging=diff,
        ))
        diff_holder.update(diff)
        return None

    resultaat = await store.beslis_op_element(slug, user_id, element_id, toepassen)
    if resultaat is None:
        raise HTTPException(status_code=404, detail=f"Onbekend annotatie-document: {slug}")
    if resultaat is GEEN_ELEMENT:
        raise HTTPException(status_code=404, detail=f"Onbekend element: {element_id}")
    if resultaat is AFGEROND:
        raise HTTPException(status_code=409, detail="Deze annotatie is afgerond. Heropen hem om te wijzigen.")
    if resultaat is VERGRENDELD:
        raise HTTPException(
            status_code=409,
            detail="Dit element is al beoordeeld. Heropen het om het te wijzigen.",
        )
    if resultaat is NIET_VERGRENDELD:
        raise HTTPException(
            status_code=409,
            detail="Dit element staat niet op slot en hoeft dus niet heropend te worden.",
        )

    # Niets veranderd, dus ook niets te melden. Zie de poort in `toepassen`.
    if geen_wijziging.get("ja"):
        return resultaat

    await store.schrijf_audit(
        slug, client_id, user_id, f"beslissing-{req.type.value}", element_id=element_id,
        detail={
            "review_reason": reden_holder["reden"].value if reden_holder["reden"] else None,
            "comment": req.comment, "diff": diff_holder,
            **({"anker_verplaatst": True} if anker_verplaatst.get("ja") else {}),
        },
    )
    return resultaat


@router.post("/documenten/{slug}/status", response_model=AnnotatieDocument)
async def zet_status(
    slug: str,
    req: StatusInvoer,
    user_id: str = Depends(actieve_userid),
    client_id: str = Depends(require_client),
    store: AnnotatieStore = Depends(get_annotatie_store),
):
    """De annotatie afronden of weer heropenen.

    Bewust een expliciete handeling van de jurist en geen afgeleide van "alle elementen beslist":
    dat laatste is niet hetzelfde als tevreden zijn — er kan nog een ronde van de agent komen, en
    de "mogelijk ontbrekend"-lijst is dan nog niet gewogen. Heropenen kan altijd; een knop die niet
    terug kan is een knop die niemand durft te gebruiken.

    Afgerond is óók bevroren: zolang de status `geaccordeerd` is weigeren alle andere schrijfpaden
    met een 409 (`_afgerond`). Dit endpoint is dus de enige uitweg — en de enige ingang.
    """
    telling = None

    def muteer(doc: AnnotatieDocument):
        nonlocal telling
        telling = tel_elementen(doc.elementen)
        doc.status = req.status
        return None

    uitkomst = await store.muteer_document(slug, user_id, muteer)
    if uitkomst is None:
        raise HTTPException(status_code=404, detail=f"Onbekend annotatie-document: {slug}")

    doc: AnnotatieDocument = uitkomst  # type: ignore[assignment]
    actie = "document-afgerond" if req.status is DocumentStatus.geaccordeerd else "document-heropend"
    await store.schrijf_audit(slug, client_id, user_id, actie, detail={
        "status": req.status.value,
        "elementen": telling.totaal if telling else 0,
        "te_beoordelen": telling.te_beoordelen if telling else 0,
    })
    return doc


@router.get("/documenten/{slug}/audit", response_model=list[AuditRecord])
async def haal_audit(
    slug: str,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(actieve_userid),
    store: AnnotatieStore = Depends(get_annotatie_store),
):
    """Append-only tijdlijn, oudste eerst. Gepagineerd: sinds elke agent-ronde per element een regel
    schrijft loopt dit bij een lange review in de honderden."""
    await _document_or_404(store, slug, user_id)
    return await store.lees_audit(slug, limit, offset)


class ExportInvoer(BaseModel):
    """Optionele bijlage bij een export: de letterlijke wettekst per lid.

    De api heeft die tekst niet — de graaf is de bron en de werkplek haalt hem al op via
    graph-qa (`GET /v1/artikel`). Meesturen mag, verzinnen niet: zonder leden blijft het
    wettekst-blok uit het rapport in plaats van dat er iets wordt gereconstrueerd.
    """

    leden: list[LidTekst] = []


@router.post("/documenten/{slug}/export")
async def exporteer_document(
    slug: str,
    req: ExportInvoer | None = None,
    formaat: str = Query("pdf", pattern="^(pdf|csv|json)$"),
    user_id: str = Depends(actieve_userid),
    store: AnnotatieStore = Depends(get_annotatie_store),
):
    """Het hele document als bestand: de markeringen als tabel plus het volledige spoor.

    Werkt in elke fase — een document dat nog in review is exporteert gewoon, met de telling
    "te beoordelen" in de kop, zodat een concept nooit als eindproduct kan worden gelezen.
    """
    doc = await _document_or_404(store, slug, user_id)

    # Het hele auditlog, niet de eerste pagina: een export die de tijdlijn halverwege afkapt is
    # erger dan geen tijdlijn, want de afkapping is in het bestand niet te zien.
    audit = []
    while True:
        blok = await store.lees_audit(slug, limit=500, offset=len(audit))
        audit.extend(blok)
        if len(blok) < 500:
            break

    export = bouw_export(doc, audit, (req.leden if req else []), formaat=formaat)
    inhoud = serialiseer(export, formaat)
    media_type = FORMATEN[formaat][0]
    naam = bestandsnaam(doc, formaat)
    return Response(
        content=inhoud,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{naam}"'},
    )
