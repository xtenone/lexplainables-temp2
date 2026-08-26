"""Tests voor genereerbare API-tokens: de service (alleen-hash-opslag, verify/revoke) en de
admin-auth via een DB-token (naast de statische env-admin-tokens). Geen netwerk."""

from __future__ import annotations

import hashlib

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


@pytest.fixture
async def db():
    from app import db as _db

    _db.init_engine("sqlite+aiosqlite://")
    await _db.create_all()
    try:
        yield _db
    finally:
        await _db.dispose_engine()


# --- service -------------------------------------------------------------------

async def test_create_slaat_alleen_hash_op(db):
    from app import api_tokens

    record, plaintext = await api_tokens.create("mijn-mcp", created_by="adm")
    assert plaintext.startswith("wa_admin_")
    assert record["label"] == "mijn-mcp"
    assert record["token_prefix"] == plaintext[:16]
    assert "token" not in record and "token_hash" not in record  # geen geheim in het record
    # In de DB staat de sha256-hash, niet de plaintext.
    async with db.get_engine().connect() as conn:
        row = (await conn.execute(select(db.api_tokens))).mappings().first()
    assert row["token_hash"] == hashlib.sha256(plaintext.encode()).hexdigest()
    assert plaintext not in str(dict(row))


async def test_verify_accepteert_geldig_en_werkt_last_used_bij(db):
    from app import api_tokens

    _, plaintext = await api_tokens.create("x")
    assert (await api_tokens.list_tokens())[0]["last_used"] is None
    assert await api_tokens.verify(plaintext) == "apitoken:x"
    assert (await api_tokens.list_tokens())[0]["last_used"] is not None


async def test_verify_weigert_onbekend_leeg_en_ingetrokken(db):
    from app import api_tokens

    assert await api_tokens.verify(None) is None
    assert await api_tokens.verify("zonder-prefix") is None
    assert await api_tokens.verify("wa_admin_nietbestaand") is None
    record, plaintext = await api_tokens.create("revoke-me")
    await api_tokens.revoke(record["id"])
    assert await api_tokens.verify(plaintext) is None


async def test_revoke_onbekend_faalt(db):
    from app import api_tokens

    with pytest.raises(api_tokens.ApiTokenError):
        await api_tokens.revoke("bestaat-niet")


# --- admin-auth via de API -----------------------------------------------------

@pytest.fixture
async def admin_client(monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("WETSANALYSE_ADMIN_TOKENS", "adm:admin-token")
    monkeypatch.setenv("WETSANALYSE_AUTH_REQUIRED", "0")
    monkeypatch.setenv("LLM_CONFIG_SECRET", Fernet.generate_key().decode())

    from app import db, ratelimit
    from app.config import get_settings
    from app.deps import get_store

    get_settings.cache_clear()
    get_store.cache_clear()
    ratelimit.reset()
    db.init_engine("sqlite+aiosqlite://")
    await db.create_all()

    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    get_store.cache_clear()
    await db.dispose_engine()


_ENV = {"Authorization": "Bearer admin-token"}


async def test_genereer_gebruik_en_intrek_token(admin_client):
    # 1. Genereer via het env-admin-token (bootstrap-pad).
    r = await admin_client.post("/v1/admin/api-tokens", headers=_ENV, json={"label": "mcp"})
    assert r.status_code == 201
    body = r.json()
    token, tid = body["token"], body["id"]
    assert token.startswith("wa_admin_")

    # 2. De lijst toont het token zonder plaintext/hash.
    lijst = (await admin_client.get("/v1/admin/api-tokens", headers=_ENV)).json()
    entry = next(t for t in lijst if t["id"] == tid)
    assert entry["label"] == "mcp" and entry["active"] is True
    assert "token" not in entry and "token_hash" not in entry

    # 3. Het gegenereerde token werkt als admin-bearer (het DB-pad in require_admin).
    db_h = {"Authorization": f"Bearer {token}"}
    assert (await admin_client.get("/v1/admin/profiles", headers=db_h)).status_code == 200

    # 4. Na intrekken werkt het token niet meer.
    assert (await admin_client.delete(f"/v1/admin/api-tokens/{tid}", headers=_ENV)).status_code == 204
    assert (await admin_client.get("/v1/admin/profiles", headers=db_h)).status_code == 401


async def test_ongeldig_token_blijft_401(admin_client):
    assert (await admin_client.get(
        "/v1/admin/api-tokens", headers={"Authorization": "Bearer wa_admin_fout"}
    )).status_code == 401
