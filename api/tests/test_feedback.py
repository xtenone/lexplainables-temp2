"""Tests voor de feedbackrouter: indienen en admin-leespad."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client(monkeypatch):
    """ASGI-client met client- én admin-auth, in-memory SQLite, geen netwerk."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite://")
    monkeypatch.setenv("WETSANALYSE_ADMIN_TOKENS", "adm:admin-token")
    monkeypatch.setenv("WETSANALYSE_AUTH_REQUIRED", "0")

    from app import db, ratelimit
    from app.config import get_settings
    from app.deps import get_annotatie_store

    get_settings.cache_clear()
    get_annotatie_store.cache_clear()
    ratelimit.reset()
    db.init_engine("sqlite+aiosqlite://")
    await db.create_all()
    # feedback_gezien_op op users bestaat alleen ná reconcile_schema (idempotente ALTER TABLE,
    # net als in productie via de lifespan) — create_all() alleen volstaat niet voor die kolom.
    await db.reconcile_schema()

    # De gescopete endpoints lopen via `actieve_userid`: die eist dat het account bestaat en actief
    # is, dus een verzonnen X-User-Id geeft 401. Zet de userids die deze tests sturen als echte
    # accounts neer ("bestaat-niet" bewust niet — die hoort juist te falen).
    from conftest import maak_testgebruikers
    await maak_testgebruikers("user1")

    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    get_annotatie_store.cache_clear()
    await db.dispose_engine()


_ADM = {"Authorization": "Bearer admin-token"}


async def test_feedback_indienen(client):
    """POST /v1/feedback geeft 201 + id terug."""
    res = await client.post(
        "/v1/feedback",
        json={"categorie": "verbeteridee", "tekst": "Knop werkt niet goed."},
        headers={"X-User-Id": "user1"},
    )
    assert res.status_code == 201
    data = res.json()
    assert "id" in data
    assert isinstance(data["id"], int)


async def test_feedback_met_pagina(client):
    """pagina-veld wordt opgeslagen."""
    res = await client.post(
        "/v1/feedback",
        json={"categorie": "compliment", "tekst": "Mooie interface!", "pagina": "/workbench"},
        headers={"X-User-Id": "user1"},
    )
    assert res.status_code == 201


async def test_feedback_ongeldige_categorie(client):
    """Ongeldige categorie → 422."""
    res = await client.post(
        "/v1/feedback",
        json={"categorie": "onbekend", "tekst": "Test."},
        headers={"X-User-Id": "user1"},
    )
    assert res.status_code == 422


async def test_feedback_lege_tekst(client):
    """Lege tekst → 422."""
    res = await client.post(
        "/v1/feedback",
        json={"categorie": "vraag", "tekst": ""},
        headers={"X-User-Id": "user1"},
    )
    assert res.status_code == 422


async def test_feedback_zonder_userid(client):
    """Ontbrekende X-User-Id → 401."""
    res = await client.post(
        "/v1/feedback",
        json={"categorie": "verbeteridee", "tekst": "Test."},
    )
    assert res.status_code == 401


async def test_admin_feedback_lijst(client):
    """GET /v1/admin/feedback geeft ingezonden items terug."""
    # Dien twee items in
    for tekst in ("Eerste bericht", "Tweede bericht"):
        await client.post(
            "/v1/feedback",
            json={"categorie": "probleemmelding", "tekst": tekst},
            headers={"X-User-Id": "user1"},
        )

    res = await client.get("/v1/admin/feedback", headers=_ADM)
    assert res.status_code == 200
    body = res.json()
    assert body["totaal"] == 2
    items = body["items"]
    assert len(items) == 2
    # Nieuwste eerst
    assert items[0]["tekst"] == "Tweede bericht"
    assert items[1]["tekst"] == "Eerste bericht"
    assert items[0]["categorie"] == "probleemmelding"
    assert "created" in items[0]


async def test_admin_feedback_zonder_token(client):
    """Admin-endpoint zonder admin-token → 401."""
    res = await client.get("/v1/admin/feedback")
    assert res.status_code == 401


async def test_lege_feedback_lijst(client):
    """Geen ingezonden feedback → lege envelope, geen 404/500."""
    res = await client.get("/v1/admin/feedback", headers=_ADM)
    assert res.status_code == 200
    assert res.json() == {"items": [], "totaal": 0}


async def test_feedback_max_length_grens(client):
    """4001 tekens overschrijdt max_length=4000 → 422."""
    res = await client.post(
        "/v1/feedback",
        json={"categorie": "vraag", "tekst": "x" * 4001},
        headers={"X-User-Id": "user1"},
    )
    assert res.status_code == 422


async def test_feedback_rate_limited(client, monkeypatch):
    """R9: herhaald indienen loopt tegen de client-rate-limit (was: require_client zonder
    limiet)."""
    from app.config import get_settings

    monkeypatch.setenv("WETSANALYSE_RATE_LIMIT_MAX", "2")
    monkeypatch.setenv("WETSANALYSE_RATE_LIMIT_WINDOW", "60")
    get_settings.cache_clear()

    codes = [
        (await client.post(
            "/v1/feedback",
            json={"categorie": "vraag", "tekst": f"Test {i}"},
            headers={"X-User-Id": "user1"},
        )).status_code
        for i in range(3)
    ]
    assert codes[:2] == [201, 201]
    assert codes[2] == 429


async def test_ongelezen_feedback_aantal_nieuwe_beheerder(client):
    """R11: een nieuwe beheerder ziet alleen feedback ingediend ná zijn eigen registratie,
    niet alle historische feedback (was: feedback_gezien_op IS NULL telde alles ooit)."""
    await client.post(
        "/v1/feedback",
        json={"categorie": "vraag", "tekst": "Oude feedback."},
        headers={"X-User-Id": "user1"},
    )

    r = await client.post(
        "/v1/admin/users", headers=_ADM,
        json={"userid": "nieuwe-beheerder", "email": "nb@test.nl", "role": "beheerder"},
    )
    assert r.status_code == 201

    await client.post(
        "/v1/feedback",
        json={"categorie": "vraag", "tekst": "Nieuwe feedback."},
        headers={"X-User-Id": "user1"},
    )

    r = await client.get(
        "/v1/admin/feedback/ongelezen-aantal", headers={**_ADM, "X-User-Id": "nieuwe-beheerder"},
    )
    assert r.status_code == 200
    assert r.json()["aantal"] == 1


async def test_markeer_gezien_onafhankelijk_per_beheerder(client):
    """Kernclaim van #283: twee beheerders houden onafhankelijke 'gezien'-tellers."""
    for uid in ("beheerder-a", "beheerder-b"):
        r = await client.post(
            "/v1/admin/users", headers=_ADM,
            json={"userid": uid, "email": f"{uid}@test.nl", "role": "beheerder"},
        )
        assert r.status_code == 201

    await client.post(
        "/v1/feedback",
        json={"categorie": "vraag", "tekst": "Feedback."},
        headers={"X-User-Id": "user1"},
    )

    r = await client.get("/v1/admin/feedback/ongelezen-aantal", headers={**_ADM, "X-User-Id": "beheerder-a"})
    assert r.json()["aantal"] == 1
    r = await client.get("/v1/admin/feedback/ongelezen-aantal", headers={**_ADM, "X-User-Id": "beheerder-b"})
    assert r.json()["aantal"] == 1

    r = await client.post("/v1/admin/feedback/markeer-gezien", headers={**_ADM, "X-User-Id": "beheerder-a"})
    assert r.status_code == 204

    r = await client.get("/v1/admin/feedback/ongelezen-aantal", headers={**_ADM, "X-User-Id": "beheerder-a"})
    assert r.json()["aantal"] == 0
    r = await client.get("/v1/admin/feedback/ongelezen-aantal", headers={**_ADM, "X-User-Id": "beheerder-b"})
    assert r.json()["aantal"] == 1


async def test_feedback_gezien_routes_vereisen_beheerder(client):
    """R12: een analist (geldige sessie, geen beheerder) krijgt 403 op de twee routes die
    huidige_beheerder gebruiken — voorheen kon elke X-User-Id hier terecht."""
    r = await client.post(
        "/v1/admin/users", headers=_ADM,
        json={"userid": "gewone-analist", "email": "ga@test.nl", "role": "analist"},
    )
    assert r.status_code == 201

    r = await client.get(
        "/v1/admin/feedback/ongelezen-aantal", headers={**_ADM, "X-User-Id": "gewone-analist"},
    )
    assert r.status_code == 403

    r = await client.post(
        "/v1/admin/feedback/markeer-gezien", headers={**_ADM, "X-User-Id": "gewone-analist"},
    )
    assert r.status_code == 403

    # Een X-User-Id die helemaal geen bestaande user is, komt er evenmin door.
    r = await client.get(
        "/v1/admin/feedback/ongelezen-aantal", headers={**_ADM, "X-User-Id": "bestaat-niet"},
    )
    assert r.status_code == 403


async def test_verwijder_feedback_happy_en_404(client):
    r = await client.post(
        "/v1/feedback",
        json={"categorie": "vraag", "tekst": "Weg ermee."},
        headers={"X-User-Id": "user1"},
    )
    feedback_id = r.json()["id"]

    r = await client.delete(f"/v1/admin/feedback/{feedback_id}", headers=_ADM)
    assert r.status_code == 204

    r = await client.get("/v1/admin/feedback", headers=_ADM)
    assert all(item["id"] != feedback_id for item in r.json()["items"])

    # Nogmaals hetzelfde id verwijderen → 404, niet stilzwijgend 204.
    r = await client.delete(f"/v1/admin/feedback/{feedback_id}", headers=_ADM)
    assert r.status_code == 404


async def test_verwijder_feedback_zonder_admintoken(client):
    r = await client.delete("/v1/admin/feedback/1")
    assert r.status_code == 401

