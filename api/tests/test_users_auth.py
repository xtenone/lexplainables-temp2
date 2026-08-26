"""Tests voor de login-module: wachtwoord-hashing, credential-verificatie (op userid), eenmalige
registratie, rol-guards, optionele 2FA (TOTP) en de HTTP-endpoints (auth + admin-gebruikersbeheer).

Inloggen gaat met de userid; e-mail is een verplicht, uniek registratiegegeven.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pyotp
import pytest
from httpx import ASGITransport, AsyncClient


def _fresh_settings(monkeypatch, **env):
    """Zet env, leeg de gecachte settings/crypto, en geef verse Settings terug."""
    from cryptography.fernet import Fernet

    from app import secrets_crypto
    from app.config import get_settings

    env.setdefault("LLM_CONFIG_SECRET", Fernet.generate_key().decode())
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    secrets_crypto._fernet.cache_clear()
    return get_settings()


@pytest.fixture
async def db():
    from app import db as _db

    _db.init_engine("sqlite+aiosqlite://")
    await _db.create_all()
    try:
        yield _db
    finally:
        await _db.dispose_engine()


def _totp_now(otpauth_uri: str) -> str:
    """Haal het secret uit een otpauth://-URI en bereken de huidige code."""
    secret = parse_qs(urlparse(otpauth_uri).query)["secret"][0]
    return pyotp.TOTP(secret).now()


# --- wachtwoord-hashing --------------------------------------------------------

def test_hash_password_round_trip():
    from app import users

    h = users.hash_password("geheim-wachtwoord")
    assert h != "geheim-wachtwoord"
    assert users.verify_password("geheim-wachtwoord", h)
    assert not users.verify_password("fout", h)
    assert not users.verify_password("x", "")


# --- eenmalige registratie -----------------------------------------------------

async def test_bootstrap_eenmalig(monkeypatch, db):
    _fresh_settings(monkeypatch)
    from app import users

    assert await users.needs_setup()
    user = await users.bootstrap_admin("Baas", "Eerste@Example.com", "wachtwoord1")
    assert user.role == "beheerder"
    assert user.userid == "baas"  # genormaliseerd
    assert user.email == "eerste@example.com"
    assert not await users.needs_setup()
    with pytest.raises(users.UserError):
        await users.bootstrap_admin("baas2", "tweede@example.com", "wachtwoord2")


async def test_userid_en_email_validatie(monkeypatch, db):
    _fresh_settings(monkeypatch)
    from app import users

    with pytest.raises(users.UserError):  # te kort / spaties
        await users.create_user("ab", "x@example.com")
    with pytest.raises(users.UserError):  # ongeldige e-mail
        await users.create_user("geldigeid", "geen-email")


# --- credential-verificatie (op userid) ----------------------------------------

async def test_verify_credentials(monkeypatch, db):
    _fresh_settings(monkeypatch)
    from app import users

    await users.bootstrap_admin("baas", "a@example.com", "goedwachtwoord")
    user, code = await users.verify_credentials("baas", "goedwachtwoord")
    assert code == "ok" and user is not None and user.role == "beheerder"

    # Inloggen met e-mail kan NIET (uitsluitend userid).
    assert (await users.verify_credentials("a@example.com", "goedwachtwoord"))[1] == "invalid"
    assert (await users.verify_credentials("baas", "fout"))[1] == "invalid"
    assert (await users.verify_credentials("onbekend", "x"))[1] == "invalid"

    # Een gedeactiveerd account kan niet inloggen (apart account; de enige beheerder is beschermd).
    _, temp = await users.create_user("analist1", "b@example.com", role="analist")
    await users.set_active("analist1", False)
    assert (await users.verify_credentials("analist1", temp))[1] == "invalid"


# --- uniciteit -----------------------------------------------------------------

async def test_unieke_userid_en_email(monkeypatch, db):
    _fresh_settings(monkeypatch)
    from app import users

    await users.create_user("jan", "jan@example.com")
    with pytest.raises(users.UserError):  # dubbele userid
        await users.create_user("jan", "anders@example.com")
    with pytest.raises(users.UserError):  # dubbele e-mail
        await users.create_user("piet", "jan@example.com")


# --- rol-guards ----------------------------------------------------------------

async def test_laatste_beheerder_beschermd(monkeypatch, db):
    _fresh_settings(monkeypatch)
    from app import users

    await users.bootstrap_admin("admin", "admin@example.com", "wachtwoord1")
    with pytest.raises(users.UserError):
        await users.set_role("admin", "analist")
    with pytest.raises(users.UserError):
        await users.set_active("admin", False)
    with pytest.raises(users.UserError):
        await users.delete_user("admin")

    # Met een tweede beheerder mag het wél.
    await users.create_user("admin2", "admin2@example.com", role="beheerder")
    await users.set_role("admin", "analist")
    assert (await users.get_user("admin")).role == "analist"


async def test_patch_user_gecombineerd_atomair(monkeypatch, db):
    """patch_user toetst de laatste-beheerder-invariant op de EIND-toestand: rol+active tegelijk
    wijzigen mag de enige beheerder niet degraderen, maar een no-op-combinatie (beheerder blijft
    actief beheerder) wél."""
    _fresh_settings(monkeypatch)
    from app import users

    await users.bootstrap_admin("admin", "admin@example.com", "wachtwoord1")
    # Rol+active in één patch die de enige beheerder zou wegnemen → geweigerd (geen half-effect).
    with pytest.raises(users.UserError):
        await users.patch_user("admin", role="analist", active=False)
    na = await users.get_user("admin")
    assert na.role == "beheerder" and na.active is True  # niets veranderd

    # Een niet-degraderende patch (blijft actief beheerder) mag.
    u = await users.patch_user("admin", role="beheerder", active=True)
    assert u.role == "beheerder" and u.active is True

    # Met een tweede beheerder mag de gecombineerde degradatie wél.
    await users.create_user("admin2", "admin2@example.com", role="beheerder")
    u = await users.patch_user("admin", role="analist", active=False)
    assert u.role == "analist" and u.active is False


async def test_verify_credentials_dummy_bcrypt_bij_onbekende_user(monkeypatch, db):
    """Bij een onbekende/inactieve gebruiker draait tóch een bcrypt-verificatie (dummy-hash), zodat
    er geen timing-oracle 'bestaat + actief' ontstaat. We toetsen het waarneembare contract: de
    reden blijft de generieke 'invalid', en de dummy-hash is een geldige bcrypt-hash."""
    _fresh_settings(monkeypatch)
    from app import users

    assert (await users.verify_credentials("bestaat-niet", "x"))[1] == "invalid"
    assert users.verify_password("x", users._DUMMY_HASH) is True


# --- stateless auth-tokens: login-ticket + trusted device ----------------------

async def test_login_ticket_roundtrip(monkeypatch, db):
    _fresh_settings(monkeypatch)
    from app import users

    t = users.maak_login_ticket("baas")
    assert t is not None
    assert users.lees_login_ticket(t) == "baas"
    assert users.lees_login_ticket("rommel") is None
    assert users.lees_login_ticket(None) is None


async def test_trusted_device_bind_invalidatie_bij_wachtwoordwijziging(monkeypatch, db):
    _fresh_settings(monkeypatch)
    from app import users

    await users.bootstrap_admin("baas", "a@example.com", "wachtwoord1")
    uri = await users.begin_2fa("baas")
    await users.activate_2fa("baas", _totp_now(uri))

    token = users.maak_trusted_device(await users.get_user("baas"))
    assert token is not None
    assert await users.valideer_trusted_device(token) == "baas"

    # Wachtwoord wijzigen verandert de bind → token automatisch ongeldig (geen revocatielijst).
    await users.change_own_password("baas", "wachtwoord1", "wachtwoord2")
    assert await users.valideer_trusted_device(token) is None


async def test_trusted_device_ongeldig_zonder_2fa(monkeypatch, db):
    _fresh_settings(monkeypatch)
    from app import users

    await users.bootstrap_admin("baas", "a@example.com", "wachtwoord1")
    # Token gemaakt vóór 2FA aanstaat: valideren moet falen (2FA niet aan).
    token = users.maak_trusted_device(await users.get_user("baas"))
    assert await users.valideer_trusted_device(token) is None


async def test_verify_credentials_via_ticket_en_trusted(monkeypatch, db):
    _fresh_settings(monkeypatch)
    from app import users

    await users.bootstrap_admin("baas", "a@example.com", "wachtwoord1")
    uri = await users.begin_2fa("baas")
    await users.activate_2fa("baas", _totp_now(uri))

    # Wachtwoord ok maar 2FA nodig.
    user, code = await users.verify_credentials("baas", "wachtwoord1")
    assert user is None and code == "totp_required"

    # Ticket telt als wachtwoord-bewijs; met geldige TOTP → ok (het 2FA-scherm zonder wachtwoord).
    ticket = users.maak_login_ticket("baas")
    user, code = await users.verify_credentials("baas", "", _totp_now(uri), ticket=ticket)
    assert code == "ok" and user is not None

    # Een ticket voor een ándere userid telt niet als bewijs.
    user, code = await users.verify_credentials("baas", "", _totp_now(uri),
                                                ticket=users.maak_login_ticket("iemand-anders"))
    # (wachtwoord leeg + ticket voor andere user → geen bewijs → invalid)
    assert user is None and code == "invalid"

    # Trusted device slaat de TOTP-stap over.
    token = users.maak_trusted_device(await users.get_user("baas"))
    user, code = await users.verify_credentials("baas", "wachtwoord1", trusted_token=token)
    assert code == "ok" and user is not None


# --- wachtwoord wijzigen -------------------------------------------------------

async def test_change_own_password(monkeypatch, db):
    _fresh_settings(monkeypatch)
    from app import users

    await users.bootstrap_admin("baas", "a@example.com", "oudwachtwoord")
    with pytest.raises(users.UserError):
        await users.change_own_password("baas", "fout", "nieuwwachtwoord")
    # De minimumlengte van het nieuwe wachtwoord wordt op de routerlaag afgedwongen
    # (Pydantic `PasswordChangeIn.new`, min_length=8), niet meer in deze service-functie —
    # zie test_change_password_te_kort_http.
    await users.change_own_password("baas", "oudwachtwoord", "nieuwwachtwoord")
    assert (await users.verify_credentials("baas", "oudwachtwoord"))[1] == "invalid"
    assert (await users.verify_credentials("baas", "nieuwwachtwoord"))[1] == "ok"


# --- 2FA (TOTP) ----------------------------------------------------------------

async def test_2fa_cyclus(monkeypatch, db):
    _fresh_settings(monkeypatch)
    from app import users

    await users.bootstrap_admin("baas", "u@example.com", "wachtwoord1")
    uri = await users.begin_2fa("baas")
    assert not (await users.get_user("baas")).totp_enabled
    assert (await users.verify_credentials("baas", "wachtwoord1"))[1] == "ok"

    with pytest.raises(users.UserError):
        await users.activate_2fa("baas", "000000")
    await users.activate_2fa("baas", _totp_now(uri))
    assert (await users.get_user("baas")).totp_enabled

    assert (await users.verify_credentials("baas", "wachtwoord1"))[1] == "totp_required"
    assert (await users.verify_credentials("baas", "wachtwoord1", "000000"))[1] == "totp_required"
    ok_user, code = await users.verify_credentials("baas", "wachtwoord1", _totp_now(uri))
    assert code == "ok" and ok_user is not None

    with pytest.raises(users.UserError):
        await users.disable_2fa("baas", "000000")
    await users.disable_2fa("baas", _totp_now(uri))
    assert not (await users.get_user("baas")).totp_enabled
    assert (await users.verify_credentials("baas", "wachtwoord1"))[1] == "ok"


# --- HTTP-endpoints ------------------------------------------------------------

@pytest.fixture
async def client(monkeypatch):
    _fresh_settings(
        monkeypatch,
        WETSANALYSE_ADMIN_TOKENS="adm:admin-token",
        WETSANALYSE_AUTH_REQUIRED="0",
    )
    from app import db, ratelimit
    from app.deps import get_store

    get_store.cache_clear()
    ratelimit.reset()
    db.init_engine("sqlite+aiosqlite://")
    await db.create_all()

    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    get_store.cache_clear()
    await db.dispose_engine()


_ADMIN = {"Authorization": "Bearer admin-token"}


async def test_setup_flow_http(client):
    r = await client.get("/v1/auth/setup-status")
    assert r.status_code == 200 and r.json()["needs_setup"] is True

    r = await client.post(
        "/v1/auth/setup", json={"userid": "baas", "email": "boss@example.com", "password": "wachtwoord1"}
    )
    assert r.status_code == 201 and r.json()["role"] == "beheerder" and r.json()["userid"] == "baas"

    r = await client.post(
        "/v1/auth/setup", json={"userid": "x", "email": "x@example.com", "password": "wachtwoord1"}
    )
    assert r.status_code == 409
    assert (await client.get("/v1/auth/setup-status")).json()["needs_setup"] is False


async def test_verify_http(client):
    await client.post(
        "/v1/auth/setup", json={"userid": "baas", "email": "boss@example.com", "password": "wachtwoord1"}
    )

    r = await client.post("/v1/auth/verify", json={"userid": "baas", "password": "wachtwoord1"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["userid"] == "baas" and body["role"] == "beheerder"

    r = await client.post("/v1/auth/verify", json={"userid": "baas", "password": "fout"})
    assert r.status_code == 200 and r.json()["ok"] is False and r.json()["code"] == "invalid"


async def test_change_password_te_kort_http(client):
    # De minimumlengte van het nieuwe wachtwoord leeft op de routerlaag (Pydantic min_length=8):
    # een te korte waarde geeft 422; een geldige wijziging slaagt (204).
    await client.post(
        "/v1/auth/setup", json={"userid": "baas", "email": "b@example.com", "password": "wachtwoord1"}
    )
    hdr = {"X-User-Id": "baas"}

    te_kort = await client.post(
        "/v1/auth/change-password", json={"current": "wachtwoord1", "new": "kort"}, headers=hdr
    )
    assert te_kort.status_code == 422

    ok = await client.post(
        "/v1/auth/change-password", json={"current": "wachtwoord1", "new": "nieuwwachtwoord"}, headers=hdr
    )
    assert ok.status_code == 204


async def test_admin_users_http(client):
    assert (await client.get("/v1/admin/users")).status_code == 401

    await client.post(
        "/v1/auth/setup", json={"userid": "baas", "email": "boss@example.com", "password": "wachtwoord1"}
    )

    r = await client.post(
        "/v1/admin/users",
        json={"userid": "analist1", "email": "analist@example.com", "role": "analist"},
        headers=_ADMIN,
    )
    assert r.status_code == 201
    temp = r.json()["temp_password"]
    assert temp and r.json()["role"] == "analist" and r.json()["userid"] == "analist1"

    v = await client.post("/v1/auth/verify", json={"userid": "analist1", "password": temp})
    assert v.json()["ok"] is True

    assert len((await client.get("/v1/admin/users", headers=_ADMIN)).json()) == 2

    p = await client.patch("/v1/admin/users/analist1", json={"role": "beheerder"}, headers=_ADMIN)
    assert p.status_code == 200 and p.json()["role"] == "beheerder"

    rp = await client.post("/v1/admin/users/analist1/reset-password", headers=_ADMIN)
    assert rp.status_code == 200 and rp.json()["temp_password"]

    d = await client.delete("/v1/admin/users/analist1", headers=_ADMIN)
    assert d.status_code == 204


async def test_2fa_http_via_header(client):
    await client.post(
        "/v1/auth/setup", json={"userid": "baas", "email": "boss@example.com", "password": "wachtwoord1"}
    )
    hdr = {"X-User-Id": "baas"}

    assert (await client.get("/v1/auth/me", headers=hdr)).json()["totp_enabled"] is False
    assert (await client.get("/v1/auth/me")).status_code == 401

    begin = await client.post("/v1/auth/2fa/begin", headers=hdr)
    assert begin.status_code == 200
    code = _totp_now(begin.json()["otpauth_uri"])

    act = await client.post("/v1/auth/2fa/activate", json={"totp": code}, headers=hdr)
    assert act.status_code == 204
    assert (await client.get("/v1/auth/me", headers=hdr)).json()["totp_enabled"] is True

    dis_fout = await client.post("/v1/auth/2fa/disable", json={"totp": "000000"}, headers=hdr)
    assert dis_fout.status_code == 400

    totp_code = _totp_now(begin.json()["otpauth_uri"])
    dis = await client.post("/v1/auth/2fa/disable", json={"totp": totp_code}, headers=hdr)
    assert dis.status_code == 204
