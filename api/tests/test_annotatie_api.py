"""Annotatie-domein (api): document-lifecycle, human-decisions, append-only audit, client-scoping."""
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
    from app.deps import get_annotatie_store, get_store

    get_settings.cache_clear()
    get_store.cache_clear()
    get_annotatie_store.cache_clear()
    ratelimit.reset()

    db.init_engine("sqlite+aiosqlite://")
    await db.create_all()

    # Document van een andere tenant — moet voor "anonymous" onzichtbaar zijn (404).
    await AnnotatieStore().maak_document(
        AnnotatieDocument(slug="andermans-doc", client_id="andere-client", bwbId="BWBR3", artikel="1")
    )

    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    get_settings.cache_clear()
    get_store.cache_clear()
    get_annotatie_store.cache_clear()
    await db.dispose_engine()


async def _maak_doc(client) -> str:
    r = await client.post(BASIS, json={"bwbId": "BWBR0004770", "artikel": "9", "werkgebied": "invordering"})
    assert r.status_code == 201
    return r.json()["slug"]


async def test_document_lifecycle_en_audit(client):
    slug = await _maak_doc(client)

    # verschijnt in de eigen lijst
    lijst = (await client.get(BASIS)).json()
    assert any(d["slug"] == slug for d in lijst)

    # voorgestelde elementen: 2 geldig + 1 ongeldige klasse (verworpen)
    r = await client.put(f"{BASIS}/{slug}/elementen", json={"elementen": [
        {"klasse": "Rechtssubject", "tekst": "de ontvanger", "lid": "1"},
        {"klasse": "Rechtsbetrekking", "tekst": "kan uitstel verlenen", "lid": "1"},
        {"klasse": "OnzinKlasse", "tekst": "iets", "lid": "1"},
    ]})
    assert r.status_code == 200
    doc = r.json()
    assert len(doc["elementen"]) == 2
    assert all(e["lifecycle"] == "voorgesteld" and e["herkomst"] == "agent" for e in doc["elementen"])
    el0, el1 = doc["elementen"][0]["id"], doc["elementen"][1]["id"]

    # approve
    doc = (await client.post(f"{BASIS}/{slug}/elementen/{el0}/beslissing", json={"type": "approve"})).json()
    assert next(e for e in doc["elementen"] if e["id"] == el0)["lifecycle"] == "human_approved"

    # edit zonder review_reason → 422
    assert (await client.post(f"{BASIS}/{slug}/elementen/{el1}/beslissing",
                              json={"type": "edit", "wijziging": {"toelichting": "beter"}})).status_code == 422
    # edit mét review_reason → edited + diff
    doc = (await client.post(f"{BASIS}/{slug}/elementen/{el1}/beslissing", json={
        "type": "edit", "review_reason": "interpretatie", "wijziging": {"toelichting": "duidelijker"},
    })).json()
    el1_obj = next(e for e in doc["elementen"] if e["id"] == el1)
    assert el1_obj["lifecycle"] == "edited" and el1_obj["herkomst"] == "mens"
    assert el1_obj["diff"]["toelichting"]["na"] == "duidelijker"

    # reject zonder review_reason → 422
    assert (await client.post(f"{BASIS}/{slug}/elementen/{el0}/beslissing",
                              json={"type": "reject"})).status_code == 422

    # audit is append-only en op volgorde: aangemaakt, elementen-voorgesteld, approve, edit
    audit = (await client.get(f"{BASIS}/{slug}/audit")).json()
    acties = [a["actie"] for a in audit]
    assert acties == ["document-aangemaakt", "elementen-voorgesteld", "beslissing-approve", "beslissing-edit"]
    assert audit[1]["detail"]["aantal"] == 2 and audit[1]["detail"]["verworpen"] == 1


async def test_aandacht_persisteert_en_zet_critic_checked(client):
    slug = await _maak_doc(client)
    r = await client.put(f"{BASIS}/{slug}/elementen", json={"elementen": [
        {"klasse": "Rechtssubject", "tekst": "de ontvanger", "lid": "1", "aandacht": "geel",
         "alternatieven": [{"klasse": "Rechtsobject", "motivatie": "twijfel"}]},
        {"klasse": "Rechtsbetrekking", "tekst": "kan uitstel verlenen", "lid": "1"},  # geen aandacht
    ]})
    assert r.status_code == 200
    elementen = r.json()["elementen"]
    met = next(e for e in elementen if e["klasse"] == "Rechtssubject")
    zonder = next(e for e in elementen if e["klasse"] == "Rechtsbetrekking")
    # aandacht gezet → gepersisteerd + lifecycle critic_checked; alternatieven bewaard.
    assert met["aandacht"] == "geel" and met["lifecycle"] == "critic_checked"
    assert met["alternatieven"][0]["klasse"] == "Rechtsobject"
    # geen aandacht → blijft voorgesteld.
    assert zonder["aandacht"] is None and zonder["lifecycle"] == "voorgesteld"


async def test_client_scoping_404(client):
    # andermans document → 404 op alle sub-resources (lekt niet)
    assert (await client.get(f"{BASIS}/andermans-doc")).status_code == 404
    assert (await client.put(f"{BASIS}/andermans-doc/elementen", json={"elementen": []})).status_code == 404
    assert (await client.get(f"{BASIS}/andermans-doc/audit")).status_code == 404
    # en niet in de eigen lijst
    assert all(d["slug"] != "andermans-doc" for d in (await client.get(BASIS)).json())


async def test_verwijderen(client):
    slug = await _maak_doc(client)
    assert (await client.delete(f"{BASIS}/{slug}")).status_code == 204
    assert (await client.get(f"{BASIS}/{slug}")).status_code == 404
