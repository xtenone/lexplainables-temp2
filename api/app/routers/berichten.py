"""Berichtensysteem — analist-resource (gemount onder /v1/berichten).

Alle endpoints vereisen een geldig client-bearer-token (`require_client`) én een `X-User-Id`-header
die de BFF uit de ingelogde sessie zet — de identiteit komt zo nooit uit browser-input.

GET  /v1/berichten/ongelezen-aantal   — aantal ongelezen gepubliceerde berichten
POST /v1/berichten/lees-alles         — markeer alle gepubliceerde berichten als gelezen
GET  /v1/berichten                    — gepubliceerde berichten met paginering en gelezen-vlag
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel

from .. import berichten as svc
from ..auth import require_client
from .auth import actieve_userid

router = APIRouter(
    prefix="/berichten",
    tags=["berichten"],
    dependencies=[Depends(require_client)],
)


# --- modellen ------------------------------------------------------------------

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


# --- endpoints (static routes vóór parameterized) ------------------------------

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
