"""De ene bron voor het gesprekken-domein (werkwijze-ADR-0011).

Persistente chatgeschiedenis van de werkplek. Anders dan het annotatie-domein (client-gescopet,
gedeeld) zijn gesprekken **per gebruiker** gescopet via `user_id` — de identiteit die de BFF uit de
ingelogde sessie als vertrouwde `X-User-Id`-header meegeeft (nooit uit browser-input). Eén rij per
gesprek; de berichten staan als aparte, geordende rijen (append-only in de praktijk: de UI voegt toe).

Bewust **los** van het annotatie-domein: een bericht kan naar een annotatie-document verwijzen
(`annotatie_slug` + het leesbare `annotatie_titel`), maar de review-state zelf blijft in het
annotatie-domein.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel
from sqlalchemy import Column, Index, Integer, String, Table, Text

from ...shared.db import DATETIME_TZ, JSON_TYPE, metadata

gesprekken = Table(
    "gesprekken",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("user_id", String(64), nullable=False, default=""),
    Column("titel", Text, nullable=False, default=""),
    Column("created", DATETIME_TZ, nullable=False),
    Column("updated", DATETIME_TZ, nullable=False),
    Index("ix_gesprekken_user_updated", "user_id", "updated"),
)

# De berichten binnen een gesprek. `inhoud` (JSON) draagt de heterogene payload van één beurt:
# {tekst, denk?, bronnen?, annotatie_slug?, annotatie_titel?, ontbrekend?}. De tijdlijn = ORDER BY id.
gesprek_berichten = Table(
    "gesprek_berichten",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("gesprek_id", String(64), nullable=False),
    Column("rol", String(16), nullable=False, default="user"),
    Column("inhoud", JSON_TYPE, nullable=False, default=dict),
    Column("created", DATETIME_TZ, nullable=False),
    Index("ix_gesprek_berichten_gesprek", "gesprek_id", "id"),
)


class Rol(str, Enum):
    user = "user"
    assistant = "assistant"


class Bericht(BaseModel):
    """Eén beurt in het gesprek. Assistent-berichten dragen optioneel `denk`/`bronnen`, of een
    verwijzing naar een annotatie-document (`annotatie_slug` + de Critic-`ontbrekend`-suggesties).

    `annotatie_titel` is het leesbare label van dat document op het moment van de beurt ("Wet IB 2001
    — art. 3.1 lid 2"). Het bericht beschrijft zichzelf dus: wordt het document later verwijderd, dan
    blijft het gesprek leesbaar in plaats van terug te vallen op een naamloze verwijzing. Oudere
    berichten hebben het veld niet en leveren "" — dat is geen fout, maar een lege terugval."""

    id: int | None = None
    rol: Rol
    tekst: str = ""
    denk: str = ""
    bronnen: list[dict] = []
    annotatie_slug: str = ""
    annotatie_titel: str = ""
    ontbrekend: list[dict] = []
    # Van welke agent-run deze beurt de uitkomst is. Dient als idempotentiesleutel: dezelfde run mag
    # maar één assistent-bericht opleveren, ook als er twee tabbladen meekeken.
    run_id: str = ""
    created: datetime | None = None


class Gesprek(BaseModel):
    """Eén chat-gesprek van een gebruiker, met zijn berichten."""

    id: str
    user_id: str = ""
    titel: str = ""
    berichten: list[Bericht] = []
    created: datetime | None = None
    updated: datetime | None = None


# --- invoer / uitvoer --------------------------------------------------------

class GesprekCreate(BaseModel):
    titel: str = ""


class GesprekPatch(BaseModel):
    titel: str


class BerichtInvoer(BaseModel):
    rol: Rol
    tekst: str = ""
    denk: str = ""
    bronnen: list[dict] = []
    annotatie_slug: str = ""
    annotatie_titel: str = ""
    ontbrekend: list[dict] = []
    run_id: str = ""


class GesprekSamenvatting(BaseModel):
    """Lichte lijst-weergave voor de sidebar (chatgeschiedenis)."""

    id: str
    titel: str = ""
    aantal_berichten: int = 0
    updated: datetime | None = None
