"""De ene bron voor het api_tokens-domein (werkwijze-ADR-0011).

Genereerbare API-tokens voor programmatische admin-toegang (bv. de admin-MCP), náást de statische
env-admin-tokens. Alleen de sha256-hash van het token wordt bewaard (tokens zijn hoog-entropie →
geen bcrypt nodig); de plaintext wordt één keer bij aanmaken getoond en nergens opgeslagen.
`token_prefix` dient enkel voor herkenning in de UI. Intrekken = `active=False` (geen delete-eis).
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, String, Table

from ...shared.db import DATETIME_TZ, metadata

api_tokens = Table(
    "api_tokens",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("label", String(128), nullable=False, default=""),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("token_prefix", String(24), nullable=False, default=""),
    Column("scope", String(16), nullable=False, default="admin"),
    Column("active", Boolean, nullable=False, default=True),
    Column("created_by", String(128), nullable=False, default=""),
    Column("created", DATETIME_TZ, nullable=False),
    Column("last_used", DATETIME_TZ, nullable=True),
)


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


def token_uit_record(t: dict) -> ApiTokenOut:
    return ApiTokenOut(
        id=t["id"], label=t["label"], token_prefix=t["token_prefix"], scope=t["scope"],
        active=t["active"], created_by=t["created_by"],
        created=t["created"].isoformat(),
        last_used=t["last_used"].isoformat() if t["last_used"] is not None else None,
    )
