"""`/v1/admin/api-tokens` — genereerbare API-tokens voor programmatische admin-toegang."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ...shared.auth import require_admin
from . import store
from .models import ApiTokenCreated, ApiTokenCreateIn, ApiTokenOut, token_uit_record

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/api-tokens", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[ApiTokenOut])
async def lijst_api_tokens():
    """Overzicht van genereerbare API-tokens — nooit de hash of het volledige token, alleen het prefix."""
    return [token_uit_record(t) for t in await store.list_tokens()]


@router.post("", response_model=ApiTokenCreated, status_code=status.HTTP_201_CREATED)
async def maak_api_token(body: ApiTokenCreateIn, admin_id: str = Depends(require_admin)):
    record, plaintext = await store.create(body.label, created_by=admin_id)
    logger.info("API-token aangemaakt", extra={
        "categorie": "security", "token_id": record["id"], "label": record["label"], "door": admin_id,
    })
    return ApiTokenCreated(**token_uit_record(record).model_dump(), token=plaintext)


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def trek_api_token_in(token_id: str, admin_id: str = Depends(require_admin)):
    try:
        await store.revoke(token_id)
    except store.ApiTokenError as e:
        raise HTTPException(status_code=404, detail=str(e))
    logger.info("API-token ingetrokken", extra={
        "categorie": "security", "token_id": token_id, "door": admin_id,
    })
