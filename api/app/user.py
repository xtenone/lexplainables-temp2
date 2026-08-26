"""Domeinmodel voor een login-account (plain Pydantic; persistentie via de store, zie users.py).

De API is de identiteitsbron van de webapp: hier leven de accounts, het wachtwoord-hash en het
(optionele) TOTP-secret. De frontend (Auth.js) houdt alleen de browsersessie. Het wachtwoord-hash
en het versleutelde TOTP-secret verlaten de server nooit via de API — responses tonen alleen
afgeleide booleans (`totp_enabled`, `active`).
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

# De twee rollen: een beheerder mag /beheer (incl. gebruikersbeheer), een analist de rest.
ROLLEN = ("beheerder", "analist")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(BaseModel):
    userid: str
    email: str = ""
    password_hash: str = ""
    role: str = "analist"
    # Versleuteld TOTP-secret (Fernet-token). None ⇒ geen 2FA gekoppeld.
    totp_secret_enc: str | None = None
    totp_enabled: bool = False
    active: bool = True

    created: datetime = Field(default_factory=_utcnow)
    updated: datetime = Field(default_factory=_utcnow)
