"""De ene bron voor het identiteit_toegang-domein (werkwijze-ADR-0011).

Login-accounts voor de webapp. De API is de identiteitsbron; de frontend (Auth.js) houdt alleen de
browsersessie. Inloggen gaat met de `userid` (de natuurlijke sleutel, lowercase genormaliseerd);
`email` is een verplicht, uniek registratiegegeven (geen inlog-identiteit). Het TOTP-secret staat
versleuteld (Fernet, zie shared.secrets_crypto) en is optioneel (2FA staat standaard uit). Het
wachtwoord-hash en het versleutelde TOTP-secret verlaten de server nooit via de API — responses
tonen alleen afgeleide booleans (`totp_enabled`, `active`).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, String, Table, Text

from ...shared.db import DATETIME_TZ, metadata, utcnow

# De twee rollen: een beheerder mag /beheer (incl. gebruikersbeheer), een analist de rest.
ROLLEN = ("beheerder", "analist")

users = Table(
    "users",
    metadata,
    Column("userid", String(64), primary_key=True),
    Column("email", String(320), nullable=False, unique=True),
    Column("password_hash", Text, nullable=False),
    Column("role", String(16), nullable=False, default="analist"),
    Column("totp_secret_enc", Text, nullable=True),
    Column("totp_enabled", Boolean, nullable=False, default=False),
    Column("active", Boolean, nullable=False, default=True),
    # Sessie-epoch: JWT-sessies met een `loginAt` vóór deze tijd zijn ongeldig (revocatie bij
    # wachtwoordwijziging/-reset). NULL = nooit gewijzigd → geen revocatie.
    Column("sessions_valid_from", DATETIME_TZ, nullable=True),
    # Tijdstip waarop een beheerder de feedbacklijst voor het laatst bekeek; NULL = nooit.
    Column("feedback_gezien_op", DATETIME_TZ, nullable=True),
    Column("created", DATETIME_TZ, nullable=False),
    Column("updated", DATETIME_TZ, nullable=False),
)


class User(BaseModel):
    userid: str
    email: str = ""
    password_hash: str = ""
    role: str = "analist"
    # Versleuteld TOTP-secret (Fernet-token). None ⇒ geen 2FA gekoppeld.
    totp_secret_enc: str | None = None
    totp_enabled: bool = False
    active: bool = True
    # Sessie-epoch: JWT-sessies met een inlogmoment vóór deze tijd zijn ongeldig (revocatie bij
    # wachtwoordwijziging/-reset). None ⇒ nooit gewijzigd → geen revocatie.
    sessions_valid_from: datetime | None = None

    created: datetime = Field(default_factory=utcnow)
    updated: datetime = Field(default_factory=utcnow)
