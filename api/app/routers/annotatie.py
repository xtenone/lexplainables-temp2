"""
De wetsanalyse-workbench-resource (gemount onder /v1/annotatie).

Vers annotatie-domein: documenten per bron, per element een human-decision (approve/edit/reject/
comment) en een append-only audit trail. Client-gescopet (404 — niet 403 — bij andermans document,
zodat het bestaan niet lekt). JAS-klassen worden gevalideerd tegen `validation.GELDIGE_JAS_KLASSEN`.

POST   /v1/annotatie/documenten                                  — maak document
GET    /v1/annotatie/documenten?limit=&offset=                   — eigen documenten (samenvatting)
GET    /v1/annotatie/documenten/{slug}                           — volledig document
DELETE /v1/annotatie/documenten/{slug}                           — verwijder eigen document
PUT    /v1/annotatie/documenten/{slug}/elementen                 — voorgestelde elementen zetten
POST   /v1/annotatie/documenten/{slug}/elementen/{id}/beslissing — human-decision
GET    /v1/annotatie/documenten/{slug}/audit                     — append-only tijdlijn
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..annotatie_contracts import (
    AnnotatieDocument, AnnotatieElement, AuditRecord, Beslissing, BeslissingInvoer, BeslissingType,
    DocumentCreate, DocumentSamenvatting, ElementenInvoer, Lifecycle,
)
from ..annotatie_store import AnnotatieStore
from ..auth import require_client
from ..db import utcnow
from ..deps import get_annotatie_store
from ..validation import GELDIGE_JAS_KLASSEN

router = APIRouter(prefix="/annotatie", tags=["annotatie"])


async def _document_or_404(store: AnnotatieStore, slug: str, client_id: str) -> AnnotatieDocument:
    """Laadt het document en dwingt eigenaarschap af. 404 (niet 403) bij mismatch — lekt niet."""
    doc = await store.laad_document(slug)
    if doc is None or doc.client_id != client_id:
        raise HTTPException(status_code=404, detail=f"Onbekend annotatie-document: {slug}")
    return doc


@router.post("/documenten", status_code=status.HTTP_201_CREATED, response_model=AnnotatieDocument)
async def maak_document(
    req: DocumentCreate,
    client_id: str = Depends(require_client),
    store: AnnotatieStore = Depends(get_annotatie_store),
):
    slug = uuid.uuid4().hex[:16]
    doc = AnnotatieDocument(
        slug=slug, client_id=client_id, werkgebied=req.werkgebied,
        bwbId=req.bwbId, artikel=req.artikel, lid=req.lid or "",
    )
    await store.maak_document(doc)
    await store.schrijf_audit(
        slug, client_id, client_id, "document-aangemaakt",
        detail={"bwbId": req.bwbId, "artikel": req.artikel, "lid": req.lid or ""},
    )
    return await store.laad_document(slug)


@router.get("/documenten", response_model=list[DocumentSamenvatting])
async def lijst_documenten(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    client_id: str = Depends(require_client),
    store: AnnotatieStore = Depends(get_annotatie_store),
):
    docs = await store.lijst_documenten(client_id, limit, offset)
    return [
        DocumentSamenvatting(
            slug=d.slug, bwbId=d.bwbId, artikel=d.artikel, lid=d.lid, werkgebied=d.werkgebied,
            status=d.status, aantal_elementen=len(d.elementen), updated=d.updated,
        )
        for d in docs
    ]


@router.get("/documenten/{slug}", response_model=AnnotatieDocument)
async def haal_document(
    slug: str,
    client_id: str = Depends(require_client),
    store: AnnotatieStore = Depends(get_annotatie_store),
):
    return await _document_or_404(store, slug, client_id)


@router.delete("/documenten/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def verwijder_document(
    slug: str,
    client_id: str = Depends(require_client),
    store: AnnotatieStore = Depends(get_annotatie_store),
):
    await _document_or_404(store, slug, client_id)
    await store.verwijder_document(slug)


@router.put("/documenten/{slug}/elementen", response_model=AnnotatieDocument)
async def zet_elementen(
    slug: str,
    req: ElementenInvoer,
    client_id: str = Depends(require_client),
    store: AnnotatieStore = Depends(get_annotatie_store),
):
    """Zet de voorgestelde elementen (van de agent). Ongeldige klasse / leeg fragment wordt verworpen."""
    await _document_or_404(store, slug, client_id)
    elementen: list[AnnotatieElement] = []
    verworpen = 0
    for e in req.elementen:
        if e.klasse not in GELDIGE_JAS_KLASSEN or not e.tekst.strip():
            verworpen += 1
            continue
        # Heeft de Critic een aandacht-niveau gezet, dan is het element al door de Critic gezien →
        # lifecycle `critic_checked`; anders `voorgesteld`.
        lifecycle = Lifecycle.critic_checked if e.aandacht is not None else Lifecycle.voorgesteld
        elementen.append(AnnotatieElement(
            id=uuid.uuid4().hex[:12], klasse=e.klasse, tekst=e.tekst, lid=e.lid,
            toelichting=e.toelichting, vindplaats=e.vindplaats, span=e.span,
            herkomst="agent", lifecycle=lifecycle, alternatieven=e.alternatieven,
            aandacht=e.aandacht, critic=e.critic,
        ))
    await store.vervang_elementen(slug, elementen)
    await store.schrijf_audit(
        slug, client_id, client_id, "elementen-voorgesteld",
        detail={"aantal": len(elementen), "verworpen": verworpen},
    )
    return await store.laad_document(slug)


@router.post("/documenten/{slug}/elementen/{element_id}/beslissing", response_model=AnnotatieDocument)
async def beslis(
    slug: str,
    element_id: str,
    req: BeslissingInvoer,
    client_id: str = Depends(require_client),
    store: AnnotatieStore = Depends(get_annotatie_store),
):
    doc = await _document_or_404(store, slug, client_id)
    el = next((x for x in doc.elementen if x.id == element_id), None)
    if el is None:
        raise HTTPException(status_code=404, detail=f"Onbekend element: {element_id}")

    diff: dict = {}
    if req.type == BeslissingType.edit:
        if req.review_reason is None:
            raise HTTPException(status_code=422, detail="review_reason is verplicht bij een edit.")
        if req.wijziging is None:
            raise HTTPException(status_code=422, detail="wijziging is verplicht bij een edit.")
        for veld in ("klasse", "tekst", "toelichting", "lid"):
            nieuw = getattr(req.wijziging, veld)
            if nieuw is not None and nieuw != getattr(el, veld):
                if veld == "klasse" and nieuw not in GELDIGE_JAS_KLASSEN:
                    raise HTTPException(status_code=422, detail=f"Ongeldige JAS-klasse: {nieuw}")
                diff[veld] = {"voor": getattr(el, veld), "na": nieuw}
                setattr(el, veld, nieuw)
        el.lifecycle = Lifecycle.edited
        el.herkomst = "mens"
        el.diff = diff
    elif req.type == BeslissingType.approve:
        el.lifecycle = Lifecycle.human_approved
    elif req.type == BeslissingType.reject:
        if req.review_reason is None:
            raise HTTPException(status_code=422, detail="review_reason is verplicht bij een reject.")
        el.lifecycle = Lifecycle.rejected
    # comment → geen lifecycle-wijziging

    el.beslissingen.append(Beslissing(
        type=req.type, actor=client_id, tijd=utcnow(),
        review_reason=req.review_reason, comment=req.comment, wijziging=diff,
    ))
    await store.vervang_elementen(slug, doc.elementen)
    await store.schrijf_audit(
        slug, client_id, client_id, f"beslissing-{req.type.value}", element_id=element_id,
        detail={
            "review_reason": req.review_reason.value if req.review_reason else None,
            "comment": req.comment, "diff": diff,
        },
    )
    return await store.laad_document(slug)


@router.get("/documenten/{slug}/audit", response_model=list[AuditRecord])
async def haal_audit(
    slug: str,
    client_id: str = Depends(require_client),
    store: AnnotatieStore = Depends(get_annotatie_store),
):
    await _document_or_404(store, slug, client_id)
    return await store.lees_audit(slug)
