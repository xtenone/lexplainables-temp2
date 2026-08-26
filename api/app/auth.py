"""Per-client bearer-tokens — erft het patroon van de MCP (tools/wettenbank-mcp/src/auth.ts).

Constant-tijd-vergelijking, fail-closed start (geen tokens ⇒ alles 401), tokens nooit loggen.
Elke geslaagde auth levert een client_id op die in de audit (job.json) belandt.
"""

from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


def authenticate(authorization: str | None, settings: Settings) -> str:
    """Valideer de Authorization-header. Geeft de client_id terug of werpt 401."""
    if not settings.auth_required:
        return "anonymous"

    if not settings.client_tokens:
        # Fail-closed: auth verplicht maar niets geconfigureerd.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Auth niet geconfigureerd (geen tokens).",
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer-token vereist.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    presented = authorization[len("Bearer ") :].strip()
    # Constant-tijd-vergelijking tegen elk bekend token.
    for token, client_id in settings.client_tokens.items():
        if hmac.compare_digest(presented, token):
            return client_id

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Ongeldig token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_client(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
    """FastAPI-dependency: geeft de client_id of werpt 401."""
    authorization = f"Bearer {credentials.credentials}" if credentials else None
    return authenticate(authorization, get_settings())


def _match_env_admin(presented: str, settings: Settings) -> str | None:
    """Constant-tijd-match tegen de statische env-admin-tokens. Geeft de admin-id of None."""
    for token, admin_id in settings.admin_tokens.items():
        if hmac.compare_digest(presented, token):
            return admin_id
    return None


def authenticate_admin(authorization: str | None, settings: Settings) -> str:
    """Valideer tegen de statische env-admin-tokens (sync pad). Geeft de admin-id of werpt 401.

    Altijd auth-plichtig (geen `auth_required`-bypass): de admin-laag beheert de LLM-config en
    mag nooit open staan. Voor het volledige pad (env + genereerbare DB-tokens) gebruik je
    `require_admin` (async).
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer-token vereist.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    presented = authorization[len("Bearer ") :].strip()
    admin_id = _match_env_admin(presented, settings)
    if admin_id is not None:
        return admin_id
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Ongeldig admin-token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_admin(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
    """FastAPI-dependency: valideer de admin-bearer en geef de admin-id, anders 401.

    Twee bronnen, in volgorde: (1) de statische env-admin-tokens (`WETSANALYSE_ADMIN_TOKENS`,
    constant-tijd), en (2) de genereerbare DB-tokens (`api_tokens.verify`, beheerd via /beheer).
    Fail-closed: geen enkele match ⇒ 401. De env-tokens blijven het bootstrap-pad (de BFF gebruikt
    ze om het eerste DB-token aan te maken)."""
    presented = credentials.credentials.strip() if credentials else None
    if presented:
        env_id = _match_env_admin(presented, get_settings())
        if env_id is not None:
            return env_id
        # Lazy import om een import-cyclus bij het laden te vermijden (api_tokens → db).
        from . import api_tokens

        db_id = await api_tokens.verify(presented)
        if db_id is not None:
            return db_id
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Ongeldig admin-token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
