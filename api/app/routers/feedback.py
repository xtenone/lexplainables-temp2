"""Gebruikersfeedback — analist-resource (gemount onder /v1/feedback).

POST /v1/feedback  — feedback indienen (client-bearer + ingelogde userid)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from .. import feedback as svc
from ..auth import require_client
from ..ratelimit import rate_limited_client
from .auth import actieve_userid

router = APIRouter(
    prefix="/feedback",
    tags=["feedback"],
    dependencies=[Depends(require_client)],
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
