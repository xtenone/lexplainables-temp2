"""Admin-resource (gemount onder /v1/admin) — LLM-modelprofielen, gebruikers en genereerbare
API-tokens beheren.

Alles achter `require_admin` (aparte admin-bearer, fail-closed). De plaintext-API-key komt
NOOIT terug in een respons: clients zien alleen `api_key_set`. Het schrijven van een key
vereist een geconfigureerde master key (LLM_CONFIG_SECRET); ontbreekt die → 400.

PUT    /v1/admin/profiles/{name}          — maak/werk profiel bij (api_key write-only)
GET    /v1/admin/profiles                 — lijst
GET    /v1/admin/profiles/{name}          — één profiel
DELETE /v1/admin/profiles/{name}          — verwijder (niet de default)
POST   /v1/admin/profiles/{name}/default  — markeer als default
POST   /v1/admin/profiles/{name}/test     — test de verbinding (kleine LLM-call)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from .. import api_tokens, berichten as berichten_svc, feedback as feedback_svc, profiles, users
from ..auth import require_admin
from ..llm.litellm_client import build_llm_client
from ..llm_profile import LlmProfile
from ..ratelimit import rate_limited_admin_test
from ..secrets_crypto import SecretsCryptoError, crypto_beschikbaar
from .auth import huidige_beheerder, vergeet_actief

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# --- modellen ------------------------------------------------------------------

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


# --- profielen -----------------------------------------------------------------

@router.get("/profiles", response_model=list[ProfileOut])
async def lijst_profielen():
    return [_to_out(p) for p in await profiles.list_profiles()]


@router.get("/profiles/{name}", response_model=ProfileOut)
async def haal_profiel(name: str):
    p = await profiles.get_profile(name)
    if p is None:
        raise HTTPException(status_code=404, detail=f"Onbekend profiel: {name}")
    return _to_out(p)


@router.put("/profiles/{name}", response_model=ProfileOut)
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


@router.delete("/profiles/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def verwijder_profiel(name: str):
    try:
        await profiles.delete_profile(name)
    except profiles.ProfileError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/profiles/{name}/default", response_model=ProfileOut)
async def maak_default(name: str):
    try:
        p = await profiles.set_default(name)
    except profiles.ProfileError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _to_out(p)


@router.post(
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


# --- gebruikersbeheer ----------------------------------------------------------

class UserOut(BaseModel):
    userid: str
    email: str
    role: str
    totp_enabled: bool
    active: bool
    created: str = ""
    updated: str = ""


class UserCreateIn(BaseModel):
    userid: str = Field(max_length=64)
    email: str = Field(max_length=320)
    role: str = Field(default="analist", max_length=16)


class UserPatchIn(BaseModel):
    role: str | None = Field(default=None, max_length=16)
    active: bool | None = None


class UserCreated(UserOut):
    # Het tijdelijke wachtwoord wordt eenmalig teruggegeven (nooit opnieuw op te vragen).
    temp_password: str


class TempPassword(BaseModel):
    userid: str
    temp_password: str


def _user_to_out(u) -> UserOut:
    return UserOut(
        userid=u.userid, email=u.email, role=u.role, totp_enabled=u.totp_enabled, active=u.active,
        created=u.created.isoformat(), updated=u.updated.isoformat(),
    )


@router.get("/users", response_model=list[UserOut])
async def lijst_users():
    return [_user_to_out(u) for u in await users.list_users()]


@router.post("/users", response_model=UserCreated, status_code=status.HTTP_201_CREATED)
async def maak_user(body: UserCreateIn):
    try:
        user, temp = await users.create_user(body.userid, body.email, role=body.role)
    except users.UserError as e:
        raise HTTPException(status_code=409, detail=str(e))
    out = _user_to_out(user)
    return UserCreated(**out.model_dump(), temp_password=temp)


@router.patch("/users/{userid}", response_model=UserOut)
async def wijzig_user(userid: str, body: UserPatchIn):
    try:
        # Rol + active in één atomaire patch (invariant op de eind-toestand — voorkomt de TOCTOU
        # waarbij twee losse checks de laatste actieve beheerder alsnog laten verdwijnen).
        user = await users.patch_user(userid, role=body.role, active=body.active)
    except users.UserError as e:
        raise HTTPException(status_code=409, detail=str(e))
    # Deactiveren moet meteen bijten, niet pas als de actief-cache verloopt.
    vergeet_actief(userid)
    return _user_to_out(user)


@router.post("/users/{userid}/reset-password", response_model=TempPassword)
async def reset_user_wachtwoord(userid: str):
    try:
        user, temp = await users.reset_password(userid)
    except users.UserError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return TempPassword(userid=user.userid, temp_password=temp)


@router.delete("/users/{userid}", status_code=status.HTTP_204_NO_CONTENT)
async def verwijder_user(userid: str):
    try:
        await users.delete_user(userid)
    except users.UserError as e:
        raise HTTPException(status_code=409, detail=str(e))
    vergeet_actief(userid)


# --- genereerbare API-tokens ---------------------------------------------------

class ApiTokenOut(BaseModel):
    id: str
    label: str = ""
    token_prefix: str = ""
    scope: str = "admin"
    active: bool = True
    created_by: str = ""
    created: str = ""
    last_used: str | None = None


class ApiTokenCreateIn(BaseModel):
    label: str = Field(default="", max_length=128)


class ApiTokenCreated(ApiTokenOut):
    # Het volledige token wordt EENMALIG teruggegeven en is daarna niet meer op te vragen.
    token: str


def _token_to_out(t: dict) -> ApiTokenOut:
    return ApiTokenOut(
        id=t["id"], label=t["label"], token_prefix=t["token_prefix"], scope=t["scope"],
        active=t["active"], created_by=t["created_by"],
        created=t["created"].isoformat(),
        last_used=t["last_used"].isoformat() if t["last_used"] is not None else None,
    )


@router.get("/api-tokens", response_model=list[ApiTokenOut])
async def lijst_api_tokens():
    """Overzicht van genereerbare API-tokens — nooit de hash of het volledige token, alleen het prefix."""
    return [_token_to_out(t) for t in await api_tokens.list_tokens()]


@router.post("/api-tokens", response_model=ApiTokenCreated, status_code=status.HTTP_201_CREATED)
async def maak_api_token(body: ApiTokenCreateIn, admin_id: str = Depends(require_admin)):
    record, plaintext = await api_tokens.create(body.label, created_by=admin_id)
    logger.info("API-token aangemaakt", extra={
        "categorie": "security", "token_id": record["id"], "label": record["label"], "door": admin_id,
    })
    return ApiTokenCreated(**_token_to_out(record).model_dump(), token=plaintext)


@router.delete("/api-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def trek_api_token_in(token_id: str, admin_id: str = Depends(require_admin)):
    try:
        await api_tokens.revoke(token_id)
    except api_tokens.ApiTokenError as e:
        raise HTTPException(status_code=404, detail=str(e))
    logger.info("API-token ingetrokken", extra={
        "categorie": "security", "token_id": token_id, "door": admin_id,
    })


# --- berichtensysteem ---------------------------------------------------------

class AdminBerichtOut(BaseModel):
    id: int
    titel: str
    inhoud: str
    type: str
    versie: str | None = None
    gepubliceerd: bool
    gepubliceerd_op: str | None = None
    aangemaakt_door: str = ""
    created: str = ""
    updated: str = ""


class BerichtAanmakenIn(BaseModel):
    titel: str = Field(max_length=256)
    inhoud: str = Field(max_length=10000)
    type: Literal["info", "update", "waarschuwing", "kritiek"] = "info"
    versie: str | None = Field(default=None, max_length=32)


class BerichtPublicatieIn(BaseModel):
    gepubliceerd: bool


def _bericht_out(row: dict) -> AdminBerichtOut:
    gp_op = row.get("gepubliceerd_op")
    return AdminBerichtOut(
        id=row["id"],
        titel=row["titel"],
        inhoud=row["inhoud"],
        type=row["type"],
        versie=row.get("versie"),
        gepubliceerd=bool(row["gepubliceerd"]),
        gepubliceerd_op=gp_op.isoformat() if gp_op else None,
        aangemaakt_door=row.get("aangemaakt_door", ""),
        created=row["created"].isoformat() if row.get("created") else "",
        updated=row["updated"].isoformat() if row.get("updated") else "",
    )


class AdminBerichtenPaginaOut(BaseModel):
    items: list[AdminBerichtOut]
    totaal: int
    pagina: int
    per_pagina: int


@router.get("/berichten", response_model=AdminBerichtenPaginaOut)
async def lijst_berichten(
    pagina: int = Query(default=1, ge=1),
    # Default ruim gehouden (i.t.t. de 20 van de analist-route): tools/wetsanalyse-admin-mcp
    # roept dit endpoint ongepagineerd aan voor de "release notes schrijven"-workflow en
    # heeft geen offset/limit-parameter om verder te bladeren — een kleinere default zou
    # oudere berichten stil onbereikbaar maken voor die tool.
    per_pagina: int = Query(default=100, ge=1, le=500),
):
    offset = (pagina - 1) * per_pagina
    rows, totaal = await asyncio.gather(
        berichten_svc.list_alle_berichten(offset=offset, limit=per_pagina),
        berichten_svc.list_alle_berichten_totaal(),
    )
    return AdminBerichtenPaginaOut(
        items=[_bericht_out(r) for r in rows],
        totaal=totaal,
        pagina=pagina,
        per_pagina=per_pagina,
    )


@router.post("/berichten", response_model=AdminBerichtOut, status_code=status.HTTP_201_CREATED)
async def maak_bericht(body: BerichtAanmakenIn, admin_id: str = Depends(require_admin)):
    row = await berichten_svc.maak_bericht(
        body.titel, body.inhoud, body.type, body.versie, admin_id
    )
    return _bericht_out(row)


@router.put("/berichten/{bericht_id}", response_model=AdminBerichtOut)
async def bewerk_bericht(bericht_id: int, body: BerichtAanmakenIn):
    try:
        row = await berichten_svc.update_bericht(bericht_id, body.titel, body.inhoud, body.type, body.versie)
    except berichten_svc.BerichtError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _bericht_out(row)


@router.patch("/berichten/{bericht_id}/publicatie", response_model=AdminBerichtOut)
async def zet_publicatie(bericht_id: int, body: BerichtPublicatieIn):
    try:
        row = await berichten_svc.set_gepubliceerd(bericht_id, body.gepubliceerd)
    except berichten_svc.BerichtError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _bericht_out(row)


@router.delete("/berichten/{bericht_id}", status_code=status.HTTP_204_NO_CONTENT)
async def verwijder_bericht(bericht_id: int):
    try:
        await berichten_svc.verwijder_bericht(bericht_id)
    except berichten_svc.BerichtError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- gebruikersfeedback --------------------------------------------------------

class FeedbackAdminOut(BaseModel):
    id: int
    client_id: str
    userid: str
    categorie: str
    tekst: str
    pagina: str | None = None
    created: str


class OngelezenFeedbackOut(BaseModel):
    aantal: int


class MarkeerGezienIn(BaseModel):
    tot: datetime | None = None


class FeedbackAdminPaginaOut(BaseModel):
    items: list[FeedbackAdminOut]
    totaal: int


@router.delete("/feedback/{feedback_id}", status_code=status.HTTP_204_NO_CONTENT)
async def verwijder_feedback(feedback_id: int):
    try:
        await feedback_svc.verwijder_feedback(feedback_id)
    except feedback_svc.FeedbackError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/feedback/ongelezen-aantal", response_model=OngelezenFeedbackOut)
async def get_ongelezen_feedback_aantal(userid: str = Depends(huidige_beheerder)):
    aantal = await feedback_svc.ongelezen_feedback_aantal(userid)
    return OngelezenFeedbackOut(aantal=aantal)


@router.post("/feedback/markeer-gezien", status_code=status.HTTP_204_NO_CONTENT)
async def post_markeer_feedback_gezien(
    body: MarkeerGezienIn = MarkeerGezienIn(), userid: str = Depends(huidige_beheerder)
):
    await feedback_svc.markeer_feedback_gezien(userid, tot=body.tot)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/feedback", response_model=FeedbackAdminPaginaOut)
async def get_feedback(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    rows, totaal = await asyncio.gather(
        feedback_svc.lijst_feedback(offset=offset, limit=limit),
        feedback_svc.lijst_feedback_totaal(),
    )
    items = [
        FeedbackAdminOut(
            **{k: v for k, v in row.items() if k != "created"},
            created=row["created"].isoformat(),
        )
        for row in rows
    ]
    return FeedbackAdminPaginaOut(items=items, totaal=totaal)
