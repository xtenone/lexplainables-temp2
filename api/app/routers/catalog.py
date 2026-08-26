"""Lichte, niet-admin catalogus-endpoints voor de client-UI.

`GET /v1/profiles` geeft alleen de bruikbare profiel-namen + welke de default is — geen provider,
model, key of verbruik (dat is admin-only via /v1/admin/profiles). `GET /v1/wetten` geeft de
keuzelijst van geregistreerde wetten (BWB-id + naam) voor de dropdown in het analyseformulier.
Zo kan de client de dropdowns vullen zonder het admin-token, terwijl het beheer admin-only blijft.

Daarnaast twee structuur-endpoints voor het analyseformulier (artikel-autocomplete + lid-keuze):
`GET /v1/wetten/{bwbId}/structuur` (afgeplatte artikellijst) en
`GET /v1/wetten/{bwbId}/artikelen/{artikel}` (leden + opschrift + snippet). Een MCP-fout met
klasse `client` (onbekende wet/artikel) wordt 404 met de actionable MCP-melding; al het overige
is een upstream-storing → 503. De data komt uit `wet_info` (TTL-cache over de MCP).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import profiles, wet_info, wetten
from ..auth import require_client
from ..deps import get_wettenbank
from ..wettenbank import WettenbankClient, WettenbankError

router = APIRouter(tags=["catalog"])


class ProfileChoice(BaseModel):
    name: str
    is_default: bool = False


class WetChoice(BaseModel):
    bwbId: str
    naam: str = ""


class ArtikelChoice(BaseModel):
    artikel: str
    pad: str = ""


class WetStructuurOut(BaseModel):
    bwbId: str
    citeertitel: str = ""
    versiedatum: str = ""
    artikelen: list[ArtikelChoice]


class LidTekst(BaseModel):
    lid: str = ""
    tekst: str = ""


class ArtikelInfoOut(BaseModel):
    bwbId: str
    artikel: str
    citeertitel: str = ""
    opschrift: str = ""
    pad: str = ""
    leden: list[str]                       # lid-nummers (voor de lid-keuzelijst)
    leden_teksten: list[LidTekst] = []     # lid + volledige tekst (voor de annotatie-workbench)
    snippet: str = ""


@router.get("/profiles", response_model=list[ProfileChoice])
async def lijst_profielen(_client_id: str = Depends(require_client)):
    items = await profiles.list_profiles()
    return [ProfileChoice(name=p.name, is_default=p.is_default) for p in items]


@router.get("/wetten", response_model=list[WetChoice])
async def lijst_wetten(_client_id: str = Depends(require_client)):
    items = await wetten.list_wetten()
    return [WetChoice(bwbId=w.bwbId, naam=w.naam) for w in items]


def _naar_http(e: WettenbankError) -> HTTPException:
    if getattr(e, "klasse", None) == "client":
        return HTTPException(status_code=404, detail=str(e))
    return HTTPException(status_code=503, detail=str(e))


@router.get("/wetten/{bwb_id}/structuur", response_model=WetStructuurOut)
async def wet_structuur(
    bwb_id: str,
    _client_id: str = Depends(require_client),
    wb: WettenbankClient = Depends(get_wettenbank),
):
    try:
        return await wet_info.structuur_overzicht(wb, bwb_id)
    except WettenbankError as e:
        raise _naar_http(e) from e


@router.get("/wetten/{bwb_id}/artikelen/{artikel}", response_model=ArtikelInfoOut)
async def wet_artikel_info(
    bwb_id: str,
    artikel: str,
    _client_id: str = Depends(require_client),
    wb: WettenbankClient = Depends(get_wettenbank),
):
    try:
        return await wet_info.artikel_info(wb, bwb_id, artikel)
    except WettenbankError as e:
        raise _naar_http(e) from e
