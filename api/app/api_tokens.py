"""Service-laag over genereerbare API-tokens (DB-backed) voor programmatische admin-toegang.

Naast de statische env-admin-tokens (`WETSANALYSE_ADMIN_TOKENS`) kan een beheerder via /beheer een
API-token **genereren** — bijvoorbeeld voor de admin-MCP. Alleen de **sha256-hash** van het token
wordt bewaard (tokens zijn hoog-entropie, dus geen bcrypt nodig); de plaintext wordt één keer bij
aanmaken teruggegeven en nergens opgeslagen. Intrekken zet `active=False`.

`verify()` is het aanknopingspunt voor `auth.require_admin`: het hasht het aangeboden token en zoekt
een actief token; bij een treffer werkt het `last_used` best-effort bij en geeft het een admin-id
terug (voor de audit). Tokens worden nooit gelogd.
"""

from __future__ import annotations

import hashlib
import secrets
from uuid import uuid4

from sqlalchemy import insert, select, update

from . import db
from .user import _utcnow

# Herkenbaar prefix + 256 bits entropie (token_urlsafe(32)). Het volledige token verlaat de server
# alleen bij aanmaken; daarna leeft alleen de hash in de DB.
TOKEN_PREFIX = "wa_admin_"
_PREFIX_SHOW = 16  # zoveel tekens bewaren we als herkenbaar (niet-bruikbaar) prefix voor de UI


class ApiTokenError(ValueError):
    """Ongeldige token-operatie (onbekend/ingetrokken)."""


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _row_to_dict(row) -> dict:
    m = dict(row)
    return {
        "id": m["id"],
        "label": m["label"],
        "token_prefix": m["token_prefix"],
        "scope": m["scope"],
        "active": bool(m["active"]),
        "created_by": m["created_by"],
        "created": db.aware(m["created"]),
        "last_used": db.aware(m["last_used"]) if m["last_used"] is not None else None,
    }


async def create(label: str, *, created_by: str = "", scope: str = "admin") -> tuple[dict, str]:
    """Genereer een nieuw token. Geeft (record-zonder-geheim, plaintext-token). Plaintext één keer."""
    plaintext = TOKEN_PREFIX + secrets.token_urlsafe(32)
    now = _utcnow()
    row = {
        "id": uuid4().hex,
        "label": (label or "").strip()[:128],
        "token_hash": _hash(plaintext),
        "token_prefix": plaintext[:_PREFIX_SHOW],
        "scope": scope,
        "active": True,
        "created_by": created_by,
        "created": now,
        "last_used": None,
    }
    async with db.get_engine().begin() as conn:
        await conn.execute(insert(db.api_tokens).values(**row))
    return _row_to_dict(row), plaintext


async def list_tokens() -> list[dict]:
    async with db.get_engine().connect() as conn:
        rows = (await conn.execute(
            select(db.api_tokens).order_by(db.api_tokens.c.created.desc())
        )).mappings().all()
    return [_row_to_dict(r) for r in rows]


async def revoke(token_id: str) -> None:
    async with db.get_engine().begin() as conn:
        res = await conn.execute(
            update(db.api_tokens).where(db.api_tokens.c.id == token_id).values(active=False)
        )
    if res.rowcount == 0:
        raise ApiTokenError(f"Onbekend token: {token_id}")


async def verify(presented: str | None) -> str | None:
    """Valideer een aangeboden token tegen de actieve DB-tokens. Geeft een admin-id of None.

    Best-effort `last_used`-update. Faalt nooit hard richting de caller (auth beslist op None).
    """
    if not presented or not presented.startswith(TOKEN_PREFIX):
        return None
    token_hash = _hash(presented)
    try:
        async with db.get_engine().begin() as conn:
            row = (await conn.execute(
                select(db.api_tokens).where(
                    db.api_tokens.c.token_hash == token_hash,
                    db.api_tokens.c.active.is_(True),
                )
            )).mappings().first()
            if row is None:
                return None
            await conn.execute(
                update(db.api_tokens).where(db.api_tokens.c.id == row["id"]).values(last_used=_utcnow())
            )
        return f"apitoken:{row['label'] or row['id'][:8]}"
    except Exception:  # noqa: BLE001 — een DB-hapering mag geen 500 worden; behandel als 'geen match'
        return None
