"""Berichtensysteem — analist-resource (`/v1/berichten`) + admin-beheer (`/v1/admin/berichten`).

De analist-routes vereisen een geldig client-bearer-token (`require_client`) én een `X-User-Id`-
header die de BFF uit de ingelogde sessie zet — de identiteit komt zo nooit uit browser-input.

GET  /v1/berichten/ongelezen-aantal   — aantal ongelezen gepubliceerde berichten
POST /v1/berichten/lees-alles         — markeer alle gepubliceerde berichten als gelezen
GET  /v1/berichten                    — gepubliceerde berichten met paginering en gelezen-vlag
"""

from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from ...shared.auth import require_admin, require_client
from ..identiteit_toegang.router import actieve_userid
from . import store as svc

router = APIRouter(
    prefix="/berichten",
    tags=["berichten"],
    dependencies=[Depends(require_client)],
)

admin_router = APIRouter(
    prefix="/admin/berichten", tags=["admin"], dependencies=[Depends(require_admin)]
)


# --- modellen (analist) ----------------------------------------------------------

class OngelezenAantalOut(BaseModel):
    aantal: int


class BerichtOut(BaseModel):
    id: int
    titel: str
    inhoud: str
    type: str
    versie: str | None = None
    gepubliceerd: bool
    gepubliceerd_op: str | None = None
    gelezen: bool = False
    created: str = ""
    updated: str = ""


class BerichtenPaginaOut(BaseModel):
    items: list[BerichtOut]
    totaal: int
    pagina: int
    per_pagina: int


def _to_out(row: dict) -> BerichtOut:
    gp_op = row.get("gepubliceerd_op")
    return BerichtOut(
        id=row["id"],
        titel=row["titel"],
        inhoud=row["inhoud"],
        type=row["type"],
        versie=row.get("versie"),
        gepubliceerd=row["gepubliceerd"],
        gepubliceerd_op=gp_op.isoformat() if gp_op else None,
        gelezen=bool(row.get("gelezen", False)),
        created=row["created"].isoformat() if row.get("created") else "",
        updated=row["updated"].isoformat() if row.get("updated") else "",
    )


# --- endpoints (static routes vóór parameterized) --------------------------------

@router.get("/ongelezen-aantal", response_model=OngelezenAantalOut)
async def get_ongelezen_aantal(userid: str = Depends(actieve_userid)):
    aantal = await svc.ongelezen_aantal(userid)
    return OngelezenAantalOut(aantal=aantal)


@router.post("/lees-alles", status_code=status.HTTP_204_NO_CONTENT)
async def post_lees_alles(userid: str = Depends(actieve_userid)):
    await svc.markeer_alles_gelezen(userid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", response_model=BerichtenPaginaOut)
async def get_berichten(
    userid: str = Depends(actieve_userid),
    pagina: int = Query(default=1, ge=1),
    per_pagina: int = Query(default=20, ge=1, le=100),
    ongelezen: bool = Query(default=False),
):
    offset = (pagina - 1) * per_pagina
    rows, totaal = await asyncio.gather(
        svc.list_berichten(userid, offset=offset, limit=per_pagina, ongelezen_only=ongelezen),
        svc.list_berichten_totaal(userid, ongelezen_only=ongelezen),
    )
    return BerichtenPaginaOut(
        items=[_to_out(r) for r in rows],
        totaal=totaal,
        pagina=pagina,
        per_pagina=per_pagina,
    )


# --- modellen (admin) --------------------------------------------------------------

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


@admin_router.get("", response_model=AdminBerichtenPaginaOut)
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
        svc.list_alle_berichten(offset=offset, limit=per_pagina),
        svc.list_alle_berichten_totaal(),
    )
    return AdminBerichtenPaginaOut(
        items=[_bericht_out(r) for r in rows],
        totaal=totaal,
        pagina=pagina,
        per_pagina=per_pagina,
    )


@admin_router.post("", response_model=AdminBerichtOut, status_code=status.HTTP_201_CREATED)
async def maak_bericht(body: BerichtAanmakenIn, admin_id: str = Depends(require_admin)):
    row = await svc.maak_bericht(
        body.titel, body.inhoud, body.type, body.versie, admin_id
    )
    return _bericht_out(row)


@admin_router.put("/{bericht_id}", response_model=AdminBerichtOut)
async def bewerk_bericht(bericht_id: int, body: BerichtAanmakenIn):
    try:
        row = await svc.update_bericht(bericht_id, body.titel, body.inhoud, body.type, body.versie)
    except svc.BerichtError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _bericht_out(row)


@admin_router.patch("/{bericht_id}/publicatie", response_model=AdminBerichtOut)
async def zet_publicatie(bericht_id: int, body: BerichtPublicatieIn):
    try:
        row = await svc.set_gepubliceerd(bericht_id, body.gepubliceerd)
    except svc.BerichtError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _bericht_out(row)


@admin_router.delete("/{bericht_id}", status_code=status.HTTP_204_NO_CONTENT)
async def verwijder_bericht(bericht_id: int):
    try:
        await svc.verwijder_bericht(bericht_id)
    except svc.BerichtError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
