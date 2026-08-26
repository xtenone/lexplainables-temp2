"""API-integratie-tests — geen engine/LLM, wel een database (in-memory SQLite)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.contracts import Job, JobState


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setenv("WETSANALYSE_AUTH_REQUIRED", "0")

    from app.config import get_settings
    from app.deps import get_store
    from app import db, ratelimit
    from app.postgres_store import PostgresStore
    get_settings.cache_clear()
    get_store.cache_clear()
    ratelimit.reset()  # globale rate-limit-staat niet laten lekken tussen tests

    db.init_engine("sqlite+aiosqlite://")
    await db.create_all()

    settings = get_settings()
    store = PostgresStore(settings)

    rapport = {
        "wet": "Testwet", "artikel": "1", "leden": [], "markeringen": [],
        "begrippen": [], "afleidingsregels": [], "reviewlog": {}, "aandachtspunten": "",
    }
    # Onder AUTH_REQUIRED=0 is de geauthenticeerde client_id "anonymous"; de testdata is
    # van diezelfde eigenaar zodat de ownership-check (IDOR) de happy path niet blokkeert.
    await store.save_job(Job(id="bwbr1-art1", state=JobState.queued, bwbId="BWBR1", artikel="1", client_id="anonymous"))
    await store.save_job(Job(id="klaar-art1", state=JobState.klaar, bwbId="BWBR2", artikel="1", client_id="anonymous"))
    await store.schrijf_rapport("klaar-art1", rapport)
    await store.save_job(Job(id="review-art1", state=JobState.wacht_review_act2, bwbId="BWBR4", artikel="1", client_id="anonymous"))
    # Project van een andere tenant — mag voor "anonymous" onzichtbaar zijn (404 + niet in lijst).
    await store.save_job(Job(id="andermans-art1", state=JobState.klaar, bwbId="BWBR3", artikel="1", client_id="andere-client"))
    await store.schrijf_rapport("andermans-art1", rapport)

    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    get_settings.cache_clear()
    get_store.cache_clear()
    await db.dispose_engine()


async def test_health(client):
    assert (await client.get("/health")).json()["status"] == "ok"


async def test_ready_en_openapi(client):
    assert "llm_model_gezet" in (await client.get("/ready")).json()
    assert (await client.get("/openapi.json")).status_code == 200


async def test_lijst_en_status(client):
    ids = {j["id"] for j in (await client.get("/v1/projects")).json()}
    assert {"bwbr1-art1", "klaar-art1"} <= ids
    assert (await client.get("/v1/projects/bwbr1-art1")).json()["state"] == "queued"
    assert (await client.get("/v1/projects/bestaat-niet")).status_code == 404


async def test_paginatie(client):
    """limit/offset begrenzen de lijst."""
    r = await client.get("/v1/projects", params={"limit": 1})
    assert r.status_code == 200 and len(r.json()) == 1


async def test_rapport_serve(client):
    r = await client.get("/v1/projects/klaar-art1/rapport")
    assert r.status_code == 200 and r.json()["wet"] == "Testwet"
    md = await client.get("/v1/projects/klaar-art1/rapport.md")
    assert md.status_code == 200 and "# Wetsanalyse" in md.text


async def test_feedback_buiten_review_409(client):
    r = await client.post("/v1/projects/bwbr1-art1/feedback", json={"status": "akkoord", "activiteit": "2"})
    assert r.status_code == 409


async def test_regelspraak_serve_en_export(client):
    """GET regelspraak-model + .rs/.md-export voor een project met een gebouwd model."""
    from app.deps import get_store
    model = {
        "werkgebied": {"naam": "Testwerkgebied"},
        "gegevensspraak": {"objecttypen": [
            {"id": "ot1", "naam": "belastingplichtige",
             "regelspraak_tekst": "Objecttype de belastingplichtige (bezield)"}
        ]},
        "regels": [{"id": "rs1", "naam": "R", "soort": "kenmerktoekenning",
                    "regelspraak_tekst": "Regel R\n  geldig altijd\n    Een belastingplichtige is x."}],
        "validatiepunten": [], "reviewlog": {},
    }
    await get_store().schrijf_regelspraak("klaar-art1", model)

    r = await client.get("/v1/projects/klaar-art1/regelspraak")
    assert r.status_code == 200 and r.json()["gegevensspraak"]["objecttypen"][0]["naam"] == "belastingplichtige"
    rs = await client.get("/v1/projects/klaar-art1/regelspraak.rs")
    assert rs.status_code == 200 and "Objecttype de belastingplichtige" in rs.text
    md = await client.get("/v1/projects/klaar-art1/regelspraak.md")
    assert md.status_code == 200 and "# RegelSpraak-specificatie" in md.text


async def test_regelspraak_nog_niet_gereed_409(client):
    assert (await client.get("/v1/projects/klaar-art1/regelspraak")).status_code == 409


async def test_regelspraak_export_nog_niet_gereed_409(client):
    """Ook de .rs/.md-export geeft een nette 409 (geen 500) als er nog geen model is."""
    assert (await client.get("/v1/projects/klaar-art1/regelspraak.rs")).status_code == 409
    assert (await client.get("/v1/projects/klaar-art1/regelspraak.md")).status_code == 409


async def test_regelspraak_start_alleen_vanuit_klaar_409(client):
    """Starten vanuit een niet-afgeronde analyse (queued) → 409."""
    r = await client.post("/v1/projects/bwbr1-art1/regelspraak", json={"review": False})
    assert r.status_code == 409


async def test_rapport_nog_niet_gereed_409(client):
    assert (await client.get("/v1/projects/bwbr1-art1/rapport")).status_code == 409


async def test_act3_en_regelspraak_scope_gates(client):
    """On-demand act3 kan alleen op een act2-only-afgeronde analyse; regelspraak juist niet."""
    from app.deps import get_store

    # klaar + scope volledig → act3 is al uitgevoerd → 409.
    r = await client.post("/v1/projects/klaar-art1/act3")
    assert r.status_code == 409 and "al uitgevoerd" in r.json()["detail"]
    # niet-klaar → 409.
    assert (await client.post("/v1/projects/bwbr1-art1/act3")).status_code == 409

    # Een act2-only-afgeronde analyse: regelspraak geweigerd, act3 gaat van start (202).
    await get_store().save_job(
        Job(id="act2-only", state=JobState.klaar, scope="act2",
            bronnen=[], client_id="anonymous")
    )
    r = await client.post("/v1/projects/act2-only/regelspraak")
    assert r.status_code == 409 and "activiteit 3" in r.json()["detail"]
    r = await client.post("/v1/projects/act2-only/act3")
    assert r.status_code == 202 and r.json()["state"] == "act3-runt"
    # De 202 schedulet de act3-fase als achtergrondtaak; netjes afkappen zodat die niet
    # ná de fixture-teardown nog de (dan gesloten) test-DB raakt.
    from app.deps import drain_tasks
    await drain_tasks()


async def test_scope_in_lijst(client):
    """JobSummary draagt de scope zodat lijst/dashboard act2-only kunnen kenmerken."""
    per_id = {j["id"]: j for j in (await client.get("/v1/projects")).json()}
    assert per_id["klaar-art1"]["scope"] == "volledig"


async def test_verwijderen_states(client):
    """Verwijderen mag vanuit een eindstaat, een review-pauze én queued (escape-hatch voor
    een verweesde job), maar niet vanuit een lopende (runt-)state."""
    from app.deps import get_store

    # runt (lopend) → 409
    await get_store().save_job(
        Job(id="runt-art1", state=JobState.act2_runt, client_id="anonymous")
    )
    assert (await client.delete("/v1/projects/runt-art1")).status_code == 409
    # queued → 204 (normaal claimt run_initial direct; blijft de job hangen, dan is dit de uitweg)
    assert (await client.delete("/v1/projects/bwbr1-art1")).status_code == 204
    assert (await client.get("/v1/projects/bwbr1-art1")).status_code == 404
    # review-pauze → 204 (de analist gooit de analyse tijdens de review weg)
    assert (await client.delete("/v1/projects/review-art1")).status_code == 204
    assert (await client.get("/v1/projects/review-art1")).status_code == 404
    # eindstaat → 204
    assert (await client.delete("/v1/projects/klaar-art1")).status_code == 204


async def test_input_limiet_422(client):
    """Te lange vrije tekst wordt door Pydantic geweigerd (422), vóór de engine wordt geraakt."""
    r = await client.post(
        "/v1/projects", json={"artikel": "1", "bwbId": "BWBR1", "analysefocus": "x" * 3000}
    )
    assert r.status_code == 422


async def test_begrippenlijst_caps_422(client):
    """De caps op de aangeleverde begrippenlijst (max 300 items, naam ≤200, definitie ≤2000)
    worden door Pydantic geweigerd (422), vóór de engine wordt geraakt."""
    bron = [{"bwbId": "BWBR1", "artikel": "1"}]
    te_veel = [{"naam": f"begrip {i}"} for i in range(301)]
    r = await client.post("/v1/projects", json={"bronnen": bron, "begrippenlijst": te_veel})
    assert r.status_code == 422
    r = await client.post("/v1/projects",
                          json={"bronnen": bron, "begrippenlijst": [{"naam": "x" * 201}]})
    assert r.status_code == 422
    r = await client.post("/v1/projects",
                          json={"bronnen": bron,
                                "begrippenlijst": [{"naam": "ok", "definitie": "x" * 2001}]})
    assert r.status_code == 422
    # Een begrip zonder naam is ongeldig (naam is het enige verplichte veld).
    r = await client.post("/v1/projects", json={"bronnen": bron, "begrippenlijst": [{"naam": ""}]})
    assert r.status_code == 422


async def test_leeg_artikel_422(client):
    """Een leeg `artikel` wordt door Pydantic geweigerd (422), vóór MCP/LLM geraakt worden."""
    r = await client.post("/v1/projects", json={"artikel": "", "bwbId": "BWBR1"})
    assert r.status_code == 422
    # Ontbrekend artikel-veld blijft eveneens 422.
    assert (await client.post("/v1/projects", json={"bwbId": "BWBR1"})).status_code == 422


async def test_tenant_isolatie(client):
    """Een project van een andere client is onzichtbaar: 404 op alle by-id-routes en
    niet aanwezig in de lijst."""
    ids = {p["id"] for p in (await client.get("/v1/projects")).json()}
    assert "andermans-art1" not in ids
    assert {"bwbr1-art1", "klaar-art1"} <= ids

    # 404 (niet 403) op de by-id-routes — bestaan mag niet lekken.
    for path in (
        "/v1/projects/andermans-art1",
        "/v1/projects/andermans-art1/rapport",
        "/v1/projects/andermans-art1/ronde/2/1",
    ):
        assert (await client.get(path)).status_code == 404, path
    assert (await client.post("/v1/projects/andermans-art1/retry")).status_code == 404
    assert (await client.delete("/v1/projects/andermans-art1")).status_code == 404


async def test_aggregate_events_route_geregistreerd(client):
    """`/v1/projects/events` is een eigen route (vóór /{project_id}), niet opgeslokt als project-id."""
    schema = (await client.get("/openapi.json")).json()
    assert "/v1/projects/events" in schema["paths"]
    assert "get" in schema["paths"]["/v1/projects/events"]


async def test_dashboard_poll_scoping_diff_en_removed(store):
    """De aggregate-poll-helper: client-scoping (geen tenant-lek), diff (alleen wijzigingen) en
    removed-signaal bij verwijdering. Getest zonder de oneindige SSE-stream."""
    from app.contracts import Job, JobState
    from app.routers.projects import _dashboard_poll

    await store.save_job(Job(id="a1", state=JobState.act2_runt, bwbId="BWBR1", artikel="1",
                             client_id="c1", model_profile="prof-x"))
    await store.save_job(Job(id="a2", state=JobState.klaar, bwbId="BWBR2", artikel="2", client_id="c1"))
    await store.save_job(Job(id="b1", state=JobState.klaar, bwbId="BWBR3", artikel="3", client_id="andere"))

    frames, seen = await _dashboard_poll(store, "c1", {})
    blob = "".join(frames)
    assert "a1" in blob and "a2" in blob
    assert "b1" not in blob  # andere tenant lekt niet
    for veld in ("current_fase", "model_profile", "tokens_in", "tokens_out", "created"):
        assert veld in blob, veld
    assert set(seen) == {"a1", "a2"}

    # Tweede poll, niets gewijzigd → geen frames.
    frames2, seen2 = await _dashboard_poll(store, "c1", seen)
    assert frames2 == []

    # Verwijder a2 → removed-frame, en a2 uit de momentopname.
    await store.delete_project("a2")
    frames3, seen3 = await _dashboard_poll(store, "c1", seen2)
    assert any("event: removed" in f and "a2" in f for f in frames3)
    assert "a2" not in seen3


async def test_dashboard_poll_geen_vals_removed_buiten_top100(store):
    """Zakt een project uit de poll-limiet (top-100 op `updated`), dan volgt géén removed-event —
    alleen een écht verwijderd project verdwijnt live uit de UI."""
    from app.routers.projects import _dashboard_poll

    await store.save_job(Job(id="oud", state=JobState.klaar, client_id="c1"))
    _, seen = await _dashboard_poll(store, "c1", {})
    assert "oud" in seen

    # 100 nieuwere projecten duwen 'oud' uit de top-100.
    for i in range(100):
        await store.save_job(Job(id=f"p{i}", state=JobState.klaar, client_id="c1"))

    frames2, seen2 = await _dashboard_poll(store, "c1", seen)
    assert not any("event: removed" in f for f in frames2)
    assert "oud" in seen2  # blijft gevolgd, ook al valt hij buiten de poll-limiet

    # Echt verwijderen → wél removed.
    await store.delete_project("oud")
    frames3, seen3 = await _dashboard_poll(store, "c1", seen2)
    assert any("event: removed" in f and "oud" in f for f in frames3)
    assert "oud" not in seen3
