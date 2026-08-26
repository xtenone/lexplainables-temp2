"""LLM-modelprofielen: de niet-admin keuzelijst (`/v1/profiles`) en het admin-beheer
(`/v1/admin/profiles/*`).

Alles onder `/admin` zit achter `require_admin` (aparte admin-bearer, fail-closed). De plaintext-
API-key komt NOOIT terug in een respons: clients zien alleen `api_key_set`. Het schrijven van een
key vereist een geconfigureerde master key (LLM_CONFIG_SECRET); ontbreekt die → 400.

GET    /v1/profiles                       — keuzelijst (naam + default) voor de client-UI
PUT    /v1/admin/profiles/{name}          — maak/werk profiel bij (api_key write-only)
GET    /v1/admin/profiles                 — lijst
GET    /v1/admin/profiles/{name}          — één profiel
DELETE /v1/admin/profiles/{name}          — verwijder (niet de default)
POST   /v1/admin/profiles/{name}/default  — markeer als default
POST   /v1/admin/profiles/{name}/test     — test de verbinding (kleine LLM-call)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ...shared.auth import require_admin, require_client
from ...shared.ratelimit import rate_limited_admin_test
from ...shared.secrets_crypto import SecretsCryptoError, crypto_beschikbaar
from . import store as profiles
from .llm.litellm_client import build_llm_client
from .models import LlmProfile

logger = logging.getLogger(__name__)

# Niet-admin keuzelijst — eigen router zonder /admin-prefix.
router = APIRouter(tags=["catalog"])

admin_router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# --- modellen ------------------------------------------------------------------

class ProfileChoice(BaseModel):
    name: str
    is_default: bool = False


class ProfileIn(BaseModel):
    provider: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=128)
    api_base: str | None = Field(default=None, max_length=512)
    api_version: str | None = Field(default=None, max_length=64)
    output_strategy: str | None = Field(default=None, max_length=32)
    temperature: float | None = None
    # Write-only: leeg/weggelaten = bestaande key ongewijzigd laten.
    api_key: str | None = Field(default=None, max_length=512)
    is_default: bool | None = None


class ProfileOut(BaseModel):
    name: str
    provider: str
    model: str
    api_base: str
    api_version: str | None = None
    output_strategy: str
    temperature: float
    is_default: bool
    api_key_set: bool
    updated_by: str = ""
    updated: str = ""


class TestResult(BaseModel):
    ok: bool
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    detail: str = ""


def _to_out(p: LlmProfile) -> ProfileOut:
    return ProfileOut(
        name=p.name,
        provider=p.provider,
        model=p.model,
        api_base=p.api_base,
        api_version=p.api_version,
        output_strategy=p.output_strategy,
        temperature=p.temperature,
        is_default=p.is_default,
        api_key_set=bool(p.enc_api_key),
        updated_by=p.updated_by,
        updated=p.updated.isoformat(),
    )


# --- niet-admin keuzelijst -------------------------------------------------------

@router.get("/profiles", response_model=list[ProfileChoice])
async def lijst_profielen_keuze(_client_id: str = Depends(require_client)):
    items = await profiles.list_profiles()
    return [ProfileChoice(name=p.name, is_default=p.is_default) for p in items]


# --- admin: profielen -----------------------------------------------------------

@admin_router.get("/profiles", response_model=list[ProfileOut])
async def lijst_profielen():
    return [_to_out(p) for p in await profiles.list_profiles()]


@admin_router.get("/profiles/{name}", response_model=ProfileOut)
async def haal_profiel(name: str):
    p = await profiles.get_profile(name)
    if p is None:
        raise HTTPException(status_code=404, detail=f"Onbekend profiel: {name}")
    return _to_out(p)


@admin_router.put("/profiles/{name}", response_model=ProfileOut)
async def upsert_profiel(name: str, body: ProfileIn, admin_id: str = Depends(require_admin)):
    if body.api_key and not crypto_beschikbaar():
        raise HTTPException(
            status_code=400,
            detail="Geen LLM_CONFIG_SECRET geconfigureerd; een API-key kan niet versleuteld worden opgeslagen.",
        )
    try:
        p = await profiles.upsert_profile(
            name,
            updated_by=admin_id,
            provider=body.provider,
            model=body.model,
            api_base=body.api_base,
            api_version=body.api_version,
            output_strategy=body.output_strategy,
            temperature=body.temperature,
            api_key=body.api_key,
            is_default=body.is_default,
        )
    except SecretsCryptoError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _to_out(p)


@admin_router.delete("/profiles/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def verwijder_profiel(name: str):
    try:
        await profiles.delete_profile(name)
    except profiles.ProfileError as e:
        raise HTTPException(status_code=409, detail=str(e))


@admin_router.post("/profiles/{name}/default", response_model=ProfileOut)
async def maak_default(name: str):
    try:
        p = await profiles.set_default(name)
    except profiles.ProfileError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _to_out(p)


@admin_router.post(
    "/profiles/{name}/test",
    response_model=TestResult,
    dependencies=[Depends(rate_limited_admin_test)],
)
async def test_profiel(name: str):
    if await profiles.get_profile(name) is None:
        raise HTTPException(status_code=404, detail=f"Onbekend profiel: {name}")
    cfg = None
    try:
        cfg = await profiles.resolve_config(name)
        client = build_llm_client(cfg)
        res = await client.complete(
            system="Je bent een verbindingstest. Antwoord uitsluitend met geldige JSON.",
            user='Geef exact: {"ok": true}',
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
        )
    except SecretsCryptoError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001 — geef een gesaniteerde melding, lek geen requestdetails
        # De ruwe provider-exceptie kan endpoint-URL's, headers of (delen van) de key
        # bevatten; die hoort in het server-log, niet in de API-respons.
        logger.warning("Verbindingstest profiel %r mislukt: %s: %s", name, type(e).__name__, e)
        return TestResult(
            ok=False,
            model=cfg.model if cfg else "",
            detail="Verbinding met de modelprovider mislukt — zie het server-log voor details.",
        )
    return TestResult(ok=True, model=res.model, tokens_in=res.tokens_in, tokens_out=res.tokens_out)
