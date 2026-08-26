"""Gebruikersfeedback — analist-resource (`/v1/feedback`) + admin-beheer (`/v1/admin/feedback`).

POST /v1/feedback  — feedback indienen (client-bearer + ingelogde userid)
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from ...shared.auth import require_admin, require_client
from ...shared.ratelimit import rate_limited_client
from ..identiteit_toegang.router import actieve_userid, huidige_beheerder
from . import store as svc

router = APIRouter(
    prefix="/feedback",
    tags=["feedback"],
    dependencies=[Depends(require_client)],
)

admin_router = APIRouter(
    prefix="/admin/feedback", tags=["admin"], dependencies=[Depends(require_admin)]
)


class FeedbackIn(BaseModel):
    categorie: str = Field(..., pattern="^(verbeteridee|probleemmelding|compliment|vraag)$")
    tekst: str = Field(..., min_length=1, max_length=4000)
    pagina: str | None = Field(None, max_length=500)


class FeedbackBevestigd(BaseModel):
    id: int


@router.post("", response_model=FeedbackBevestigd, status_code=status.HTTP_201_CREATED)
async def post_feedback(
    body: FeedbackIn,
    client_id: str = Depends(rate_limited_client),
    userid: str = Depends(actieve_userid),
):
    feedback_id = await svc.dien_in(
        client_id=client_id,
        userid=userid,
        categorie=body.categorie,
        tekst=body.tekst,
        pagina=body.pagina,
    )
    return FeedbackBevestigd(id=feedback_id)


# --- admin -------------------------------------------------------------------

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


@admin_router.delete("/{feedback_id}", status_code=status.HTTP_204_NO_CONTENT)
async def verwijder_feedback(feedback_id: int):
    try:
        await svc.verwijder_feedback(feedback_id)
    except svc.FeedbackError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_router.get("/ongelezen-aantal", response_model=OngelezenFeedbackOut)
async def get_ongelezen_feedback_aantal(userid: str = Depends(huidige_beheerder)):
    aantal = await svc.ongelezen_feedback_aantal(userid)
    return OngelezenFeedbackOut(aantal=aantal)


@admin_router.post("/markeer-gezien", status_code=status.HTTP_204_NO_CONTENT)
async def post_markeer_feedback_gezien(
    body: MarkeerGezienIn = MarkeerGezienIn(), userid: str = Depends(huidige_beheerder)
):
    await svc.markeer_feedback_gezien(userid, tot=body.tot)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_router.get("", response_model=FeedbackAdminPaginaOut)
async def get_feedback(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    rows, totaal = await asyncio.gather(
        svc.lijst_feedback(offset=offset, limit=limit),
        svc.lijst_feedback_totaal(),
    )
    items = [
        FeedbackAdminOut(
            **{k: v for k, v in row.items() if k != "created"},
            created=row["created"].isoformat(),
        )
        for row in rows
    ]
    return FeedbackAdminPaginaOut(items=items, totaal=totaal)
