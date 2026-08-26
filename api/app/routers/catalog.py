"""Lichte, niet-admin catalogus-endpoints voor de client-UI.

`GET /v1/profiles` geeft alleen de bruikbare profiel-namen + welke de default is — geen provider,
model, key of verbruik (dat is admin-only via /v1/admin/profiles). Zo vult de client de
profiel-dropdown zonder het admin-token, terwijl het beheer admin-only blijft.

De wet-keuzelijst en de structuur/artikel-lookups zijn verwijderd: de werkplek draait op de graaf
(graph-qa levert de wettekst via `GET /v1/artikel`), dus de API heeft de wettenbank-MCP niet meer
nodig.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import profiles
from ..auth import require_client

router = APIRouter(tags=["catalog"])


class ProfileChoice(BaseModel):
    name: str
    is_default: bool = False


@router.get("/profiles", response_model=list[ProfileChoice])
async def lijst_profielen(_client_id: str = Depends(require_client)):
    items = await profiles.list_profiles()
    return [ProfileChoice(name=p.name, is_default=p.is_default) for p in items]
