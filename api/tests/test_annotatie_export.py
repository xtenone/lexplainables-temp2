"""Export van een annotatiedocument (pdf/csv/json) + de registratie van de productie-metadata.

Twee dingen worden hier bewaakt die makkelijk stil wegvallen: dat de export het VOLLEDIGE spoor
draagt (beslissingen, Critic-rondes, anker, diff, model) en dat de herkomst van een voorstel — met
welk model het gemaakt is — blijft staan zodra hij één keer geregistreerd is.
"""
from __future__ import annotations

import csv
import io
import json

import pytest
from httpx import ASGITransport, AsyncClient

BASIS = "/v1/annotatie/documenten"

RUN = {
    "ronde": 1, "model": "claude-sonnet-4-6", "provider": "anthropic_via_azure_foundry",
    "agent_versie": "0.4.0", "critic_rondes": 2, "stop_reden": "convergentie",
}


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setenv("WETSANALYSE_AUTH_REQUIRED", "0")

    from app import db, ratelimit
    from app.config import get_settings
    from app.deps import get_annotatie_store
    from conftest import maak_testgebruikers

    get_settings.cache_clear()
    get_annotatie_store.cache_clear()
    ratelimit.reset()

    db.init_engine("sqlite+aiosqlite://")
    await db.create_all()
    await maak_testgebruikers("gebruiker-a")

    from app.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"X-User-Id": "gebruiker-a"}
    ) as ac:
        yield ac

    get_settings.cache_clear()
    get_annotatie_store.cache_clear()
    await db.dispose_engine()


async def _document_met_spoor(client) -> str:
    """Een document met een agent-ronde (mét run), een beslissing en een eigen markering."""
    slug = (await client.post(BASIS, json={
        "bwbId": "BWBR0004770", "artikel": "9", "lid": "2", "werkgebied": "invordering",
    })).json()["slug"]

    r = await client.put(f"{BASIS}/{slug}/elementen", json={
        "ronde": 1, "run": RUN,
        "elementen": [
            {"id": "m1", "klasse": "Rechtssubject", "tekst": "de belastingschuldige", "lid": "2",
             "vindplaats": "BWBR0004770 art. 9 lid 2", "toelichting": "drager van plichten",
             "aandacht": "geel", "critic": "let op de afbakening",
             "critic_rondes": [{"ronde": 1, "aandacht": "geel", "motivatie": "te ruim", "actie": "behoud"}],
             "alternatieven": [{"klasse": "Rechtsobject", "motivatie": "kan ook"}],
             "anker": {"lid": "2", "start": 4, "eind": 24, "bron_hash": "abc123"}},
            {"id": "m2", "klasse": "Voorwaarde", "tekst": "indien de aanslag is opgelegd", "lid": "2"},
        ],
    })
    assert r.status_code == 200

    await client.post(f"{BASIS}/{slug}/elementen/m1/beslissing", json={
        "type": "edit", "review_reason": "verkeerde_klasse",
        "wijziging": {"klasse": "Rechtsobject"}, "comment": "toch een object",
    })
    await client.post(f"{BASIS}/{slug}/elementen", json={
        "klasse": "Tijdsaanduiding", "tekst": "binnen zes weken", "lid": "2",
    })
    return slug


async def test_run_wordt_geregistreerd_op_document_element_en_audit(client):
    slug = await _document_met_spoor(client)

    doc = (await client.get(f"{BASIS}/{slug}")).json()
    assert doc["runs"] == [{**RUN, "tijd": doc["runs"][0]["tijd"]}]
    agent = {e["id"]: e for e in doc["elementen"] if e["herkomst"] == "agent"}
    assert agent["m2"]["geproduceerd_door"]["model"] == "claude-sonnet-4-6"
    assert agent["m2"]["geproduceerd_door"]["agent_versie"] == "0.4.0"
    # De eigen markering van de jurist heeft geen model — die is niet geproduceerd.
    mens = next(e for e in doc["elementen"] if e["herkomst"] == "mens")
    assert mens["geproduceerd_door"] is None

    audit = (await client.get(f"{BASIS}/{slug}/audit")).json()
    ronde = next(a for a in audit if a["actie"] == "elementen-voorgesteld")
    assert ronde["detail"]["model"] == "claude-sonnet-4-6"
    assert ronde["detail"]["critic_rondes"] == 2


async def test_ronde_zonder_run_wist_bestaande_herkomst_niet(client):
    """Een oudere client die geen run meestuurt mag het spoor niet uitgummen."""
    slug = await _document_met_spoor(client)

    r = await client.put(f"{BASIS}/{slug}/elementen", json={
        "ronde": 2,
        "elementen": [{"id": "m2", "klasse": "Voorwaarde", "tekst": "indien de aanslag is opgelegd",
                       "lid": "2", "toelichting": "aangevuld"}],
    })
    assert r.status_code == 200
    m2 = next(e for e in r.json()["elementen"] if e["id"] == "m2")
    assert m2["toelichting"] == "aangevuld"
    assert m2["geproduceerd_door"]["model"] == "claude-sonnet-4-6"
    assert len(r.json()["runs"]) == 1


async def test_export_json_draagt_het_volledige_spoor(client):
    slug = await _document_met_spoor(client)

    r = await client.post(f"{BASIS}/{slug}/export?formaat=json", json={
        "leden": [{"lid": "2", "tekst": "De belastingschuldige betaalt binnen zes weken."}],
    })
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert 'filename="annotatie-BWBR0004770-art9-lid2-' in r.headers["content-disposition"]

    data = json.loads(r.content)
    assert data["export"]["versie"] == "1"
    assert data["document"]["modellen"] == ["claude-sonnet-4-6"]
    assert data["leden"][0]["lid"] == "2"
    assert data["telling"]["totaal"] == 3
    assert data["telling"]["van_jurist"] == 1
    assert data["audit"], "het auditlog hoort mee te komen"

    op_id = {e["id"]: e for e in data["elementen"]}
    m1 = op_id["m1"]
    assert m1["klasse"] == "Rechtsobject"                  # de edit is toegepast
    assert m1["diff"]["klasse"] == {"voor": "Rechtssubject", "na": "Rechtsobject"}
    assert m1["beslissingen"][0]["review_reason"] == "verkeerde_klasse"
    assert m1["critic_rondes"][0]["motivatie"] == "te ruim"
    assert m1["alternatieven"][0]["klasse"] == "Rechtsobject"
    assert m1["anker"]["bron_hash"] == "abc123"
    assert m1["kleur"].startswith("#")


async def test_export_volgt_de_canonieke_jas_volgorde(client):
    slug = await _document_met_spoor(client)
    data = json.loads((await client.post(f"{BASIS}/{slug}/export?formaat=json")).content)
    # Rechtsobject (2) → Voorwaarde (5) → Tijdsaanduiding (10), ongeacht invoervolgorde.
    assert [e["klasse"] for e in data["elementen"]] == ["Rechtsobject", "Voorwaarde", "Tijdsaanduiding"]
    assert [e["volgnummer"] for e in data["elementen"]] == [1, 2, 3]


async def test_export_csv_is_excel_leesbaar(client):
    slug = await _document_met_spoor(client)
    r = await client.post(f"{BASIS}/{slug}/export?formaat=csv")
    assert r.status_code == 200
    assert r.content.startswith(b"\xef\xbb\xbf"), "BOM ontbreekt — Excel verminkt dan de diacritieken"

    tekst = r.content.decode("utf-8-sig")
    assert "# modellen;claude-sonnet-4-6" in tekst
    rijen = list(csv.reader(io.StringIO(tekst), delimiter=";"))
    kop = next(i for i, rij in enumerate(rijen) if rij and rij[0] == "nr")
    data = [rij for rij in rijen[kop + 1:] if rij]
    assert len(data) == 3
    assert data[0][1] == "Rechtsobject"
    assert data[0][2].startswith("#")            # kleur_hex, want CSV kent geen opmaak
    assert "claude-sonnet-4-6" in data[0]


async def test_export_pdf_is_een_pdf(client):
    slug = await _document_met_spoor(client)
    r = await client.post(f"{BASIS}/{slug}/export?formaat=pdf", json={
        "leden": [{"lid": "2", "tekst": "De belastingschuldige betaalt binnen zes weken."}],
    })
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-")
    assert len(r.content) > 2000


async def test_export_van_leeg_en_onbekend_document(client):
    """Een verse annotatie exporteert gewoon; andermans slug bestaat niet."""
    slug = (await client.post(BASIS, json={"bwbId": "BWBR1", "artikel": "1"})).json()["slug"]
    for formaat in ("json", "csv", "pdf"):
        assert (await client.post(f"{BASIS}/{slug}/export?formaat={formaat}")).status_code == 200

    assert (await client.post(f"{BASIS}/bestaat-niet/export?formaat=json")).status_code == 404
    assert (await client.post(f"{BASIS}/{slug}/export?formaat=docx")).status_code == 422


async def test_document_zonder_run_toont_model_als_onbekend(client):
    """Documenten van vóór de registratie: geen leeg veld, maar een expliciete melding."""
    slug = (await client.post(BASIS, json={"bwbId": "BWBR1", "artikel": "1"})).json()["slug"]
    await client.put(f"{BASIS}/{slug}/elementen", json={
        "ronde": 1, "elementen": [{"klasse": "Operator", "tekst": "vermeerderd met"}],
    })
    data = json.loads((await client.post(f"{BASIS}/{slug}/export?formaat=json")).content)
    assert data["document"]["runs"] == []
    assert data["elementen"][0]["model"] == "onbekend (vóór registratie)"


async def test_pdf_verdraagt_tekens_die_op_opmaak_lijken(client):
    """Wettekst en modeluitvoer mogen `<` en `&` bevatten; reportlab leest een alinea als markup.

    Eén zo'n teken zonder escape breekt het hele document — en dat is precies het soort fout dat
    pas bij een echte wettekst opvalt.
    """
    slug = (await client.post(BASIS, json={"bwbId": "BWBR1", "artikel": "1"})).json()["slug"]
    await client.put(f"{BASIS}/{slug}/elementen", json={
        "ronde": 1, "run": RUN,
        "elementen": [{"klasse": "Operator", "tekst": "a < b & c",
                       "toelichting": "<b>niet als opmaak lezen</b>"}],
    })
    r = await client.post(f"{BASIS}/{slug}/export?formaat=pdf", json={
        "leden": [{"lid": "1", "tekst": "Indien a < b & c, dan geldt <deze> regel."}],
    })
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-")


async def test_bestaande_rij_zonder_runs_kolom(client):
    """De `runs`-kolom wordt additief bijgezet: bestaande rijen houden NULL, geen lege lijst.

    `reconcile_schema` voegt kolommen toe zónder NOT NULL, dus dit is precies wat er op productie
    gebeurt bij de eerste start na deze wijziging. Leest de store dat niet op als [], dan valt elk
    bestaand document om — en dat merk je pas dáár.
    """
    from sqlalchemy import update

    from app import db

    slug = (await client.post(BASIS, json={"bwbId": "BWBR1", "artikel": "1"})).json()["slug"]
    async with db.get_engine().begin() as conn:
        await conn.execute(
            update(db.annotatie_documenten)
            .where(db.annotatie_documenten.c.slug == slug)
            .values(runs=None)
        )

    doc = (await client.get(f"{BASIS}/{slug}")).json()
    assert doc["runs"] == []
    assert (await client.post(f"{BASIS}/{slug}/export?formaat=json")).status_code == 200

