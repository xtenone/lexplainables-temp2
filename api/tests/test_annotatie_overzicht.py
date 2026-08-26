"""Het annotatie-overzicht: afronden/heropenen en de verrijkte samenvatting.

Dit is de data waarop de werkvoorraad van de jurist draait — "wat moet ik nog beoordelen". Loopt de
telling uit de pas met het document, dan wijst het overzicht mensen naar het verkeerde werk.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

BASIS = "/v1/annotatie/documenten"


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setenv("WETSANALYSE_AUTH_REQUIRED", "0")

    from app import db, ratelimit
    from app.annotatie_contracts import AnnotatieDocument
    from app.annotatie_store import AnnotatieStore
    from app.config import get_settings
    from app.deps import get_annotatie_store
    from conftest import maak_testgebruikers

    get_settings.cache_clear()
    get_annotatie_store.cache_clear()
    ratelimit.reset()

    db.init_engine("sqlite+aiosqlite://")
    await db.create_all()
    await maak_testgebruikers("gebruiker-a", "gebruiker-b")

    await AnnotatieStore().maak_document(
        AnnotatieDocument(slug="andermans-doc", user_id="gebruiker-b", client_id="x",
                          bwbId="BWBR3", artikel="1")
    )

    from app.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"X-User-Id": "gebruiker-a"}
    ) as ac:
        yield ac

    get_settings.cache_clear()
    get_annotatie_store.cache_clear()
    await db.dispose_engine()


async def _doc_met_elementen(client) -> str:
    slug = (await client.post(BASIS, json={
        "bwbId": "BWBR0004770", "artikel": "9", "citeertitel": "Invorderingswet 1990",
    })).json()["slug"]
    await client.put(f"{BASIS}/{slug}/elementen", json={
        "ronde": 1,
        "run": {"ronde": 1, "model": "claude-sonnet-4-6", "provider": "azure", "agent_versie": "1.0"},
        "elementen": [
            {"id": "m1", "klasse": "Rechtssubject", "tekst": "de ontvanger", "aandacht": "rood",
             "critic": "te ruim"},
            {"id": "m2", "klasse": "Voorwaarde", "tekst": "indien de aanslag is opgelegd",
             "aandacht": "geel"},
            {"id": "m3", "klasse": "Rechtssubject", "tekst": "de belastingschuldige"},
        ],
    })
    return slug


async def test_samenvatting_draagt_de_werkvoorraad(client):
    slug = await _doc_met_elementen(client)
    await client.post(f"{BASIS}/{slug}/elementen/m1/beslissing", json={"type": "approve"})

    rij = next(d for d in (await client.get(BASIS)).json() if d["slug"] == slug)
    assert rij["citeertitel"] == "Invorderingswet 1990"
    assert rij["aantal_elementen"] == 3
    assert rij["te_beoordelen"] == 2                      # m1 is beslist
    assert rij["per_aandacht"] == {"rood": 1, "geel": 1, "geen": 1}
    assert rij["per_klasse"] == {"Rechtssubject": 2, "Voorwaarde": 1}
    assert rij["laatste_model"] == "claude-sonnet-4-6"
    assert rij["status"] == "in_review"


async def test_citeertitel_valt_terug_op_werkgebied(client):
    """Documenten van vóór het aparte veld dragen de wetnaam nog in `werkgebied`."""
    slug = (await client.post(BASIS, json={
        "bwbId": "BWBR1", "artikel": "1", "werkgebied": "Zorgverzekeringswet",
    })).json()["slug"]
    rij = next(d for d in (await client.get(BASIS)).json() if d["slug"] == slug)
    assert rij["citeertitel"] == "Zorgverzekeringswet"

    kaal = (await client.post(BASIS, json={"bwbId": "BWBR2", "artikel": "1"})).json()["slug"]
    rij = next(d for d in (await client.get(BASIS)).json() if d["slug"] == kaal)
    assert rij["citeertitel"] == "BWBR2"


async def test_afronden_en_heropenen(client):
    slug = await _doc_met_elementen(client)

    r = await client.post(f"{BASIS}/{slug}/status", json={"status": "geaccordeerd"})
    assert r.status_code == 200
    assert r.json()["status"] == "geaccordeerd"
    assert next(d for d in (await client.get(BASIS)).json() if d["slug"] == slug)["status"] == "geaccordeerd"

    audit = (await client.get(f"{BASIS}/{slug}/audit")).json()
    afgerond = next(a for a in audit if a["actie"] == "document-afgerond")
    assert afgerond["detail"]["te_beoordelen"] == 3      # afronden mag ook met open elementen
    assert afgerond["actor"] == "gebruiker-a"

    r = await client.post(f"{BASIS}/{slug}/status", json={"status": "in_review"})
    assert r.json()["status"] == "in_review"
    assert any(a["actie"] == "document-heropend" for a in (await client.get(f"{BASIS}/{slug}/audit")).json())


async def test_een_afgerond_document_is_bevroren(client):
    """`geaccordeerd` blokkeerde eerder niets: er kon daarna nog van alles bij, af en overheen — ook
    door een nieuwe agent-ronde. Afronden is nu een slot, met heropenen als enige uitweg."""
    slug = await _doc_met_elementen(client)
    await client.post(f"{BASIS}/{slug}/status", json={"status": "geaccordeerd"})

    agentronde = await client.put(f"{BASIS}/{slug}/elementen", json={
        "ronde": 2, "elementen": [{"id": "m1", "klasse": "Rechtsfeit", "tekst": "de ontvanger"}],
    })
    eigen = await client.post(f"{BASIS}/{slug}/elementen", json={
        "klasse": "Rechtsobject", "tekst": "de aanslag", "lid": "1",
    })
    beslissing = await client.post(f"{BASIS}/{slug}/elementen/m2/beslissing", json={"type": "approve"})
    weg = await client.delete(f"{BASIS}/{slug}/elementen/m1")

    for r in (agentronde, eigen, beslissing, weg):
        assert r.status_code == 409, r.text
        assert "afgerond" in r.json()["detail"]

    doc = (await client.get(f"{BASIS}/{slug}")).json()
    assert [e["id"] for e in doc["elementen"]] == ["m1", "m2", "m3"]
    assert doc["elementen"][0]["klasse"] == "Rechtssubject"

    # Heropenen maakt alles weer los.
    await client.post(f"{BASIS}/{slug}/status", json={"status": "in_review"})
    assert (await client.post(f"{BASIS}/{slug}/elementen/m2/beslissing",
                              json={"type": "approve"})).status_code == 200


async def test_status_van_anderen_en_ongeldige_toestand(client):
    slug = await _doc_met_elementen(client)
    # Promoveren naar de graaf hoort bij het (nog niet bestaande) schrijfpad, niet bij de jurist.
    assert (await client.post(f"{BASIS}/{slug}/status", json={"status": "gepromoveerd"})).status_code == 422
    assert (await client.post(f"{BASIS}/{slug}/status", json={"status": "onzin"})).status_code == 422
    # Andermans document bestaat niet voor deze gebruiker.
    assert (await client.post(f"{BASIS}/andermans-doc/status", json={"status": "geaccordeerd"})).status_code == 404


async def test_afronden_raakt_de_elementen_niet(client):
    """De status-mutatie loopt door hetzelfde schrijfpad als de elementen; die mogen niet meeschuiven."""
    slug = await _doc_met_elementen(client)
    voor = (await client.get(f"{BASIS}/{slug}")).json()["elementen"]

    await client.post(f"{BASIS}/{slug}/status", json={"status": "geaccordeerd"})

    na = (await client.get(f"{BASIS}/{slug}")).json()["elementen"]
    assert [e["id"] for e in na] == [e["id"] for e in voor]
    assert na[0]["geproduceerd_door"]["model"] == "claude-sonnet-4-6"
