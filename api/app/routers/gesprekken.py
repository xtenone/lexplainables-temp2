"""
De gesprekken-resource (gemount onder /v1/gesprekken): de persistente chatgeschiedenis van de werkplek.

**Per-gebruiker gescopet** — anders dan het client-gescopete annotatie-domein. De identiteit komt uit
de vertrouwde `X-User-Id`-header die de BFF uit de ingelogde sessie zet (`huidige_userid`, hergebruikt
uit de auth-router); de router zit achter de client-bearer (`require_client`), zoals de auth-router.
404 (niet 403) bij andermans gesprek, zodat het bestaan niet lekt.

POST   /v1/gesprekken                       — nieuw gesprek
GET    /v1/gesprekken?limit=&offset=        — eigen gesprekken (samenvatting, nieuwste eerst)
GET    /v1/gesprekken/{id}                  — volledig gesprek (met berichten)
POST   /v1/gesprekken/{id}/berichten        — bericht toevoegen
PATCH  /v1/gesprekken/{id}                  — titel wijzigen
DELETE /v1/gesprekken/{id}                  — verwijder eigen gesprek
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import require_client
from ..deps import get_gesprek_store
from ..gesprek_contracts import (
    Bericht, BerichtInvoer, Gesprek, GesprekCreate, GesprekPatch, GesprekSamenvatting,
)
from ..gesprek_store import GesprekStore
from .auth import actieve_userid

router = APIRouter(prefix="/gesprekken", tags=["gesprekken"], dependencies=[Depends(require_client)])


async def _gesprek_or_404(store: GesprekStore, gesprek_id: str, user_id: str) -> Gesprek:
    """Laadt het gesprek en dwingt eigenaarschap af. 404 (niet 403) bij mismatch — lekt niet."""
    gesprek = await store.laad_gesprek(gesprek_id)
    if gesprek is None or gesprek.user_id != user_id:
        raise HTTPException(status_code=404, detail=f"Onbekend gesprek: {gesprek_id}")
    return gesprek


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Gesprek)
async def maak_gesprek(
    req: GesprekCreate,
    user_id: str = Depends(actieve_userid),
    store: GesprekStore = Depends(get_gesprek_store),
):
    gesprek = Gesprek(id=uuid.uuid4().hex[:16], user_id=user_id, titel=req.titel)
    await store.maak_gesprek(gesprek)
    return await store.laad_gesprek(gesprek.id)


@router.get("", response_model=list[GesprekSamenvatting])
async def lijst_gesprekken(
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(actieve_userid),
    store: GesprekStore = Depends(get_gesprek_store),
):
    return await store.lijst_samenvattingen(user_id, limit, offset)


@router.get("/{gesprek_id}", response_model=Gesprek)
async def haal_gesprek(
    gesprek_id: str,
    user_id: str = Depends(actieve_userid),
    store: GesprekStore = Depends(get_gesprek_store),
):
    return await _gesprek_or_404(store, gesprek_id, user_id)


@router.post("/{gesprek_id}/berichten", status_code=status.HTTP_201_CREATED, response_model=Bericht)
async def voeg_bericht_toe(
    gesprek_id: str,
    req: BerichtInvoer,
    user_id: str = Depends(actieve_userid),
    store: GesprekStore = Depends(get_gesprek_store),
):
    await _gesprek_or_404(store, gesprek_id, user_id)
    return await store.voeg_bericht_toe(gesprek_id, req)


@router.patch("/{gesprek_id}", response_model=Gesprek)
async def hernoem_gesprek(
    gesprek_id: str,
    req: GesprekPatch,
    user_id: str = Depends(actieve_userid),
    store: GesprekStore = Depends(get_gesprek_store),
):
    await _gesprek_or_404(store, gesprek_id, user_id)
    await store.hernoem_gesprek(gesprek_id, req.titel)
    return await store.laad_gesprek(gesprek_id)


@router.delete("/{gesprek_id}", status_code=status.HTTP_204_NO_CONTENT)
async def verwijder_gesprek(
    gesprek_id: str,
    user_id: str = Depends(actieve_userid),
    store: GesprekStore = Depends(get_gesprek_store),
):
    await _gesprek_or_404(store, gesprek_id, user_id)
    await store.verwijder_gesprek(gesprek_id)
