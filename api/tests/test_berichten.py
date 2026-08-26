"""Tests voor het berichtensysteem: service (berichten + leesbewijzen) en router-autorisatie."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def db():
    from app import db as _db

    _db.init_engine("sqlite+aiosqlite://")
    await _db.create_all()
    try:
        yield _db
    finally:
        await _db.dispose_engine()


@pytest.fixture
async def client(monkeypatch):
    """ASGI-client met cliënt- én admin-auth, geen netwerk."""
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

    # De gescopete endpoints lopen via `actieve_userid`: die eist dat het account bestaat en actief
    # is, dus een verzonnen X-User-Id geeft 401. Zet de userids die deze tests sturen als echte
    # accounts neer ("bestaat-niet" bewust niet — die hoort juist te falen).
    from conftest import maak_testgebruikers
    await maak_testgebruikers("user1", "user2", "irrelevant")

    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    get_annotatie_store.cache_clear()
    await db.dispose_engine()


_ADM = {"Authorization": "Bearer admin-token"}


async def _insert_user(db, userid: str, email: str | None = None) -> None:
    """Hulpfunctie: voeg een user-rij in (nodig voor de new-user guard in berichten-queries)."""
    from sqlalchemy import insert
    from app.db import utcnow

    async with db.get_engine().begin() as conn:
        await conn.execute(insert(db.users).values(
            userid=userid,
            email=email or f"{userid}@test.nl",
            password_hash="x",
            role="analist",
            active=True,
            created=utcnow(),
            updated=utcnow(),
        ))


# --- service: basis CRUD -------------------------------------------------------

async def test_maak_en_lijst(db):
    from app import berichten as svc

    row = await svc.maak_bericht("Titel", "Inhoud", "info", None, "adm")
    assert row["id"] is not None
    assert row["gepubliceerd"] is False
    assert row["type"] == "info"

    alle = await svc.list_alle_berichten()
    assert any(r["id"] == row["id"] for r in alle)


async def test_publiceer_en_zichtbaar_voor_analist(db):
    from app import berichten as svc

    # User vóór bericht aanmaken (new-user guard: berichten.created >= users.created).
    await _insert_user(db, "user1")

    row = await svc.maak_bericht("Update", "Iets nieuws.", "update", "v1.0", "adm")
    bericht_id = row["id"]

    # Ongepubliceerd → niet zichtbaar voor analist.
    assert await svc.list_berichten("user1") == []

    await svc.set_gepubliceerd(bericht_id, True)

    berichten = await svc.list_berichten("user1")
    assert len(berichten) == 1
    assert berichten[0]["gelezen"] is False


async def test_ongelezen_aantal_basis(db):
    from app import berichten as svc

    # User vóór bericht aanmaken (new-user guard).
    await _insert_user(db, "u1")

    assert await svc.ongelezen_aantal("u1") == 0

    row = await svc.maak_bericht("Bericht", "Tekst", "info", None, "adm")
    await svc.set_gepubliceerd(row["id"], True)

    assert await svc.ongelezen_aantal("u1") == 1

    await svc.markeer_alles_gelezen("u1")
    assert await svc.ongelezen_aantal("u1") == 0


async def test_markeer_alles_gelezen_is_idempotent(db):
    from app import berichten as svc

    # User vóór bericht aanmaken (new-user guard).
    await _insert_user(db, "u1")

    row = await svc.maak_bericht("B", "T", "info", None, "adm")
    await svc.set_gepubliceerd(row["id"], True)

    # Twee keer aanroepen mag geen fout geven.
    await svc.markeer_alles_gelezen("u1")
    await svc.markeer_alles_gelezen("u1")


async def test_verwijder_cascade_leesbewijzen(db):
    from app import berichten as svc
    from app import db as _db
    from sqlalchemy import func, select

    # User vóór bericht aanmaken (new-user guard).
    await _insert_user(db, "u1")

    row = await svc.maak_bericht("B", "T", "info", None, "adm")
    await svc.set_gepubliceerd(row["id"], True)
    await svc.markeer_alles_gelezen("u1")

    # Leesbewijs bestaat.
    async with _db.get_engine().connect() as conn:
        cnt = await conn.scalar(
            select(func.count()).select_from(_db.bericht_leesbewijzen)
            .where(_db.bericht_leesbewijzen.c.bericht_id == row["id"])
        )
    assert cnt == 1

    await svc.verwijder_bericht(row["id"])

    # Leesbewijs is mee verwijderd.
    async with _db.get_engine().connect() as conn:
        cnt2 = await conn.scalar(
            select(func.count()).select_from(_db.bericht_leesbewijzen)
            .where(_db.bericht_leesbewijzen.c.bericht_id == row["id"])
        )
    assert cnt2 == 0


async def test_verwijder_onbekend_gooit_error(db):
    from app import berichten as svc

    with pytest.raises(svc.BerichtError):
        await svc.verwijder_bericht(9999)


async def test_nieuwe_user_ziet_geen_historische_berichten(db):
    """New-user guard: berichten aangemaakt vóór de user-account worden niet getoond."""
    from app import berichten as svc

    # Bericht VÓÓR de user aanmaken — mag daarna niet zichtbaar zijn.
    row = await svc.maak_bericht("Oud", "Historisch.", "info", None, "adm")
    await svc.set_gepubliceerd(row["id"], True)

    # User pas daarna aanmelden.
    await _insert_user(db, "nieuw")

    berichten = await svc.list_berichten("nieuw")
    assert all(b["id"] != row["id"] for b in berichten)
    assert await svc.ongelezen_aantal("nieuw") == 0


async def test_concept_voor_registratie_publicatie_erna_is_zichtbaar(db):
    """R1: een concept geschreven vóór de user-registratie, maar pas ná registratie
    gepubliceerd, moet wél zichtbaar zijn — de zichtbaarheid volgt het publicatiemoment,
    niet het aanmaakmoment van het concept."""
    from app import berichten as svc

    # Concept vóór de user-registratie.
    row = await svc.maak_bericht("Concept", "Nog niet gepubliceerd.", "info", None, "adm")

    # User registreert zich ná het aanmaken van het concept.
    await _insert_user(db, "later-geregistreerd")

    # Publicatie gebeurt nog weer later.
    await svc.set_gepubliceerd(row["id"], True)

    berichten = await svc.list_berichten("later-geregistreerd")
    assert any(b["id"] == row["id"] for b in berichten)
    assert await svc.ongelezen_aantal("later-geregistreerd") == 1


async def test_markeer_alles_gelezen_concurrent(db):
    """R2: gelijktijdige aanroepen (twee tabbladen, React StrictMode) mogen niet op een
    duplicate-key-fout lopen, en leveren precies één leesbewijs per bericht op."""
    import asyncio
    from sqlalchemy import func, select
    from app import berichten as svc
    from app import db as _db

    await _insert_user(db, "concurrent-user")
    row = await svc.maak_bericht("B", "T", "info", None, "adm")
    await svc.set_gepubliceerd(row["id"], True)

    # Geen exception, ook niet bij gelijktijdige uitvoering.
    await asyncio.gather(*(svc.markeer_alles_gelezen("concurrent-user") for _ in range(5)))

    async with _db.get_engine().connect() as conn:
        cnt = await conn.scalar(
            select(func.count()).select_from(_db.bericht_leesbewijzen)
            .where(_db.bericht_leesbewijzen.c.bericht_id == row["id"])
            .where(_db.bericht_leesbewijzen.c.userid == "concurrent-user")
        )
    assert cnt == 1


async def test_verwijder_bericht_onbekend_doet_geen_wijziging(db):
    """verwijder_bericht op een onbekend id doet geen enkele write vóór de 404 — geen
    no-op-commit meer (was: de leesbewijzen-delete committede alsnog). Bewijs: een
    bestaand bericht blijft byte-voor-byte ongewijzigd na een faalpoging op een ander id."""
    from app import berichten as svc

    await svc.maak_bericht("Blijft staan", "Ongewijzigd.", "info", None, "adm")
    voor = await svc.list_alle_berichten()
    assert len(voor) == 1

    with pytest.raises(svc.BerichtError):
        await svc.verwijder_bericht(9999)

    na = await svc.list_alle_berichten()
    assert voor == na


async def test_lege_lijst_alle_berichten(db):
    from app import berichten as svc

    assert await svc.list_alle_berichten() == []
    assert await svc.list_alle_berichten_totaal() == 0


# --- router: autorisatie -------------------------------------------------------

async def test_analist_mag_geen_admin_berichten(client):
    # Zonder admin-token → 401.
    r = await client.get("/v1/admin/berichten")
    assert r.status_code == 401


async def test_admin_maak_en_publiceer(client):
    r = await client.post(
        "/v1/admin/berichten",
        headers=_ADM,
        json={"titel": "Titel", "inhoud": "Inhoud.", "type": "update"},
    )
    assert r.status_code == 201
    bericht_id = r.json()["id"]

    r = await client.patch(
        f"/v1/admin/berichten/{bericht_id}/publicatie",
        headers=_ADM,
        json={"gepubliceerd": True},
    )
    assert r.status_code == 200
    assert r.json()["gepubliceerd"] is True


async def test_admin_weigert_ongeldig_type(client):
    r = await client.post(
        "/v1/admin/berichten",
        headers=_ADM,
        json={"titel": "T", "inhoud": "I.", "type": "hack"},
    )
    assert r.status_code == 422


async def test_analist_ziet_gepubliceerd_bericht(client):
    # Uniek userid zodat herhaalde runs geen 409 geven als de DB toestand deelt.
    userid = "analist-ziet-bericht"
    # User vóór bericht aanmaken (new-user guard).
    await client.post("/v1/admin/users", headers=_ADM, json={"userid": userid, "email": f"{userid}@test.nl"})

    # Maak + publiceer via admin.
    r = await client.post(
        "/v1/admin/berichten",
        headers=_ADM,
        json={"titel": "Nieuw", "inhoud": "Tekst.", "type": "info"},
    )
    bericht_id = r.json()["id"]
    await client.patch(
        f"/v1/admin/berichten/{bericht_id}/publicatie",
        headers=_ADM,
        json={"gepubliceerd": True},
    )

    # Analist haalt lijst op (envelope-formaat met items/totaal/pagina/per_pagina).
    r = await client.get("/v1/berichten", headers={"X-User-Id": userid})
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "totaal" in body
    ids = [b["id"] for b in body["items"]]
    assert bericht_id in ids


async def test_ongelezen_aantal_route_basis(client):
    """Route retourneert 0 voor een gebruiker zonder berichten."""
    r = await client.get("/v1/berichten/ongelezen-aantal", headers={"X-User-Id": "user2"})
    assert r.status_code == 200
    assert r.json()["aantal"] == 0


async def test_lees_alles_route(client):
    """Volledige flow: bericht aanmaken, publiceren, ongelezen tellen, alles markeren."""
    userid = "lees-alles-user"
    # User vóór bericht aanmaken.
    await client.post("/v1/admin/users", headers=_ADM, json={"userid": userid, "email": f"{userid}@test.nl"})

    r = await client.post(
        "/v1/admin/berichten", headers=_ADM,
        json={"titel": "T", "inhoud": "I.", "type": "info"},
    )
    await client.patch(
        f"/v1/admin/berichten/{r.json()['id']}/publicatie",
        headers=_ADM, json={"gepubliceerd": True},
    )

    r = await client.get("/v1/berichten/ongelezen-aantal", headers={"X-User-Id": userid})
    assert r.json()["aantal"] == 1

    r = await client.post("/v1/berichten/lees-alles", headers={"X-User-Id": userid})
    assert r.status_code == 204

    r = await client.get("/v1/berichten/ongelezen-aantal", headers={"X-User-Id": userid})
    assert r.json()["aantal"] == 0


async def test_ongelezen_route_vereist_user_id(client):
    """Zonder X-User-Id header → 401 (huidige_userid dependency)."""
    r = await client.get("/v1/berichten/ongelezen-aantal")
    assert r.status_code == 401


async def test_paginering_pagina2(client):
    """Pagina 2 met per_pagina=2 geeft het derde bericht terug."""
    userid = "pagina2-user"
    await client.post("/v1/admin/users", headers=_ADM, json={"userid": userid, "email": f"{userid}@test.nl"})

    ids = []
    for i in range(3):
        r = await client.post(
            "/v1/admin/berichten", headers=_ADM,
            json={"titel": f"Bericht {i}", "inhoud": "Tekst.", "type": "info"},
        )
        ids.append(r.json()["id"])
        await client.patch(
            f"/v1/admin/berichten/{ids[-1]}/publicatie",
            headers=_ADM, json={"gepubliceerd": True},
        )

    r = await client.get("/v1/berichten?pagina=2&per_pagina=2", headers={"X-User-Id": userid})
    assert r.status_code == 200
    body = r.json()
    assert body["pagina"] == 2
    assert body["totaal"] == 3
    assert len(body["items"]) == 1


async def test_ongeldige_pagina_geeft_422(client):
    """pagina=0 voldoet niet aan ge=1 → 422 Unprocessable Entity."""
    r = await client.get("/v1/berichten?pagina=0", headers={"X-User-Id": "irrelevant"})
    assert r.status_code == 422


async def test_ongelezen_filter(client):
    """?ongelezen=true geeft alleen ongelezen berichten terug."""
    userid = "ongelezen-filter-user"
    await client.post("/v1/admin/users", headers=_ADM, json={"userid": userid, "email": f"{userid}@test.nl"})

    r = await client.post(
        "/v1/admin/berichten", headers=_ADM,
        json={"titel": "Ongelezen", "inhoud": "Tekst.", "type": "info"},
    )
    bericht_id = r.json()["id"]
    await client.patch(
        f"/v1/admin/berichten/{bericht_id}/publicatie",
        headers=_ADM, json={"gepubliceerd": True},
    )

    # Vóór markeren: filter geeft het bericht terug.
    r = await client.get("/v1/berichten?ongelezen=true", headers={"X-User-Id": userid})
    assert r.status_code == 200
    assert any(b["id"] == bericht_id for b in r.json()["items"])

    # Na markeren: filter geeft geen berichten meer.
    await client.post("/v1/berichten/lees-alles", headers={"X-User-Id": userid})
    r = await client.get("/v1/berichten?ongelezen=true", headers={"X-User-Id": userid})
    assert r.json()["items"] == []


async def test_admin_berichten_paginering(client):
    """GET /v1/admin/berichten pagineert (envelope items/totaal/pagina/per_pagina)."""
    ids = []
    for i in range(3):
        r = await client.post(
            "/v1/admin/berichten", headers=_ADM,
            json={"titel": f"Admin-bericht {i}", "inhoud": "Tekst.", "type": "info"},
        )
        ids.append(r.json()["id"])

    r = await client.get("/v1/admin/berichten?pagina=2&per_pagina=1", headers=_ADM)
    assert r.status_code == 200
    body = r.json()
    assert body["pagina"] == 2
    assert body["per_pagina"] == 1
    assert body["totaal"] == 3
    assert len(body["items"]) == 1
