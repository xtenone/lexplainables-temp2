"""Tests voor de RegelSpraak-vervolgfase (on-demand op een afgeronde analyse).

Spiegelt test_engine.py: dezelfde FakeLLM/FakeWettenbank, in-memory SQLite-store. Dekt de
autonome doorloop, beide review-checkpoints, de feedback-lus, het mislukt-starten op een niet-
afgeronde analyse, en de tekstexport.
"""

import pytest

from conftest import FakeLLM, FakeWettenbank

from app.contracts import BronInput, Feedback, FoutKlasse, JobState, StartRequest
from app.engine.orchestrator import WetsanalyseEngine


def _start_req(review: bool) -> StartRequest:
    return StartRequest(bronnen=[BronInput(bwbId="BWBR9999999", artikel="1")], review=review)


async def _tot_klaar(engine):
    """Breng een analyse autonoom tot `klaar` en geef de job-id terug."""
    job = await engine.create_job(_start_req(review=False), "test")
    await engine.run_initial(job.id)
    return job.id


class _RsGeenHerkomstLLM(FakeLLM):
    """Brongetrouw voor act-2/act-3, maar laat de `herkomst` weg in de RegelSpraak-output, zodat de
    HARDE brongetrouwheid-check (herkomst verplicht) faalt. act-2/3 blijven ongemoeid (die dragen geen
    objecttypen/regels), dus de analyse bereikt gewoon `klaar`."""

    async def complete(self, system: str, user: str, schema=None):
        res = await super().complete(system, user, schema)
        if isinstance(res.data, dict):
            for groep in ("objecttypen", "feittypen", "parameters", "domeinen"):
                for item in res.data.get(groep) or []:
                    item.pop("herkomst", None)
            for regel in res.data.get("regels") or []:
                regel.pop("herkomst", None)
        return res


class _RsDanglingHerkomstLLM(FakeLLM):
    """Brongetrouw, maar verwijst in de RegelSpraak-herkomst naar een begrip/regel dat niet in het
    rapport bestaat (b999/r999). De herkomst is wél aanwezig — de aanwezigheidscheck slaagt — maar de
    integriteit-cross-check tegen de ingest moet 'm als harde schending vangen (job → fout)."""

    async def complete(self, system: str, user: str, schema=None):
        res = await super().complete(system, user, schema)
        if isinstance(res.data, dict):
            for groep in ("objecttypen", "feittypen", "parameters", "domeinen"):
                for item in res.data.get(groep) or []:
                    if item.get("herkomst"):
                        item["herkomst"]["begrip_ids"] = ["b999"]
            for regel in res.data.get("regels") or []:
                if regel.get("herkomst"):
                    regel["herkomst"]["regel_id"] = "r999"
        return res


class _RsOngedektLLM(FakeLLM):
    """Brongetrouw en herleidbaar (vindplaatsen blijven), maar laat de `begrip_ids` weg zodat het
    rapport-begrip b1 door geen enkele declaratie wordt gedekt. Dat is geen harde schending (de
    herkomst is aanwezig via vindplaatsen) maar moet als dekking-waarschuwing landen."""

    async def complete(self, system: str, user: str, schema=None):
        res = await super().complete(system, user, schema)
        if isinstance(res.data, dict):
            for groep in ("objecttypen", "feittypen", "parameters", "domeinen"):
                for item in res.data.get(groep) or []:
                    if item.get("herkomst"):
                        item["herkomst"].pop("begrip_ids", None)
        return res


async def test_regelspraak_autonoom_tot_rs_klaar(engine, store):
    job_id = await _tot_klaar(engine)
    await engine.run_regelspraak(job_id, review=False)

    job = await store.load_job(job_id)
    assert job.state == JobState.rs_klaar
    model = await store.lees_regelspraak(job_id)
    assert model is not None
    assert model["gegevensspraak"]["objecttypen"][0]["naam"] == "belastingplichtige"
    assert model["regels"][0]["id"] == "rs1"
    assert model["regels"][0]["herkomst"]["regel_id"] == "r1"
    # Provenance: act-2 + act-3 (2) + rs-gegevens + rs-regels (2) = 4 rondes.
    activiteiten = [p.activiteit for p in job.provenance]
    assert "rs-gegevens" in activiteiten and "rs-regels" in activiteiten


async def test_regelspraak_start_alleen_vanuit_klaar(engine, store):
    """run_regelspraak op een nog niet afgeronde analyse doet niets (claim faalt)."""
    job = await engine.create_job(_start_req(review=True), "test")
    await engine.run_initial(job.id)  # blijft hangen op wacht-review-act2
    assert (await store.load_job(job.id)).state == JobState.wacht_review_act2

    await engine.run_regelspraak(job.id, review=False)
    # Onveranderd: geen regelspraak gestart.
    assert (await store.load_job(job.id)).state == JobState.wacht_review_act2
    assert await store.lees_regelspraak(job.id) is None


async def test_regelspraak_review_checkpoints(engine, store):
    job_id = await _tot_klaar(engine)
    await engine.run_regelspraak(job_id, review=True)

    # Eerste checkpoint: GegevensSpraak.
    assert (await store.load_job(job_id)).state == JobState.wacht_review_rs_gegevens
    await engine.apply_feedback(job_id, Feedback(status="akkoord", activiteit="rs-gegevens"))

    # Tweede checkpoint: regels.
    assert (await store.load_job(job_id)).state == JobState.wacht_review_rs_regels
    await engine.apply_feedback(job_id, Feedback(status="akkoord", activiteit="rs-regels"))

    job = await store.load_job(job_id)
    assert job.state == JobState.rs_klaar
    assert (await store.lees_regelspraak(job_id)) is not None


async def test_regelspraak_feedback_maakt_nieuwe_ronde(engine, store):
    job_id = await _tot_klaar(engine)
    await engine.run_regelspraak(job_id, review=True)

    # Wijzigingen op de GegevensSpraak → ronde 2, opnieuw in review.
    await engine.apply_feedback(
        job_id,
        Feedback(status="wijzigingen", activiteit="rs-gegevens",
                 items={"ot1": "Voeg een attribuut toe."}),
    )
    job = await store.load_job(job_id)
    assert job.state == JobState.wacht_review_rs_gegevens
    assert job.current_ronde == 2
    assert await store.hoogste_ronde(job_id, "rs-gegevens") == 2


async def test_regelspraak_review_inherit_van_job(engine, store):
    """review=None erft Job.review (hier False via de autonome analyse) → loopt door tot rs_klaar."""
    job_id = await _tot_klaar(engine)
    await engine.run_regelspraak(job_id, review=None)
    assert (await store.load_job(job_id)).state == JobState.rs_klaar


async def test_regelspraak_export_rs_en_md(engine, store):
    from app.engine.render_regelspraak import render_md, render_rs

    job_id = await _tot_klaar(engine)
    await engine.run_regelspraak(job_id, review=False)
    model = await store.lees_regelspraak(job_id)

    rs = render_rs(model)
    assert "Objecttype de belastingplichtige" in rs
    assert "Regel Beslis aangifteplicht" in rs

    md = render_md(model)
    assert "# RegelSpraak-specificatie" in md
    assert "## 1. GegevensSpraak" in md


# --- brongetrouwheid, retry en de akkoord-her-validatie (A4) ------------------

async def test_regelspraak_brongetrouwheid_fout_ook_review_false(settings, store):
    """Ontbrekende herkomst → job naar `fout` (ook in review:false); nooit stil een model opleveren."""
    eng = WetsanalyseEngine(settings, store, _RsGeenHerkomstLLM(), FakeWettenbank())
    job_id = await _tot_klaar(eng)
    await eng.run_regelspraak(job_id, review=False)

    job = await store.load_job(job_id)
    assert job.state == JobState.fout
    assert job.error.klasse == FoutKlasse.validatie
    assert await store.lees_regelspraak(job_id) is None


async def test_regelspraak_dangling_herkomst_faalt(settings, store):
    """Een herkomst-id dat niet in de wetsanalyse bestaat (b999) → harde schending → job naar `fout`,
    ook in review:false. Aanwezige-maar-ongeldige herkomst is net zo onherleidbaar als ontbrekende."""
    eng = WetsanalyseEngine(settings, store, _RsDanglingHerkomstLLM(), FakeWettenbank())
    job_id = await _tot_klaar(eng)
    await eng.run_regelspraak(job_id, review=False)

    job = await store.load_job(job_id)
    assert job.state == JobState.fout
    assert job.error.klasse == FoutKlasse.validatie
    assert "b999" in (job.error.bericht or "") or any("b999" in w for w in job.waarschuwingen)
    assert await store.lees_regelspraak(job_id) is None


async def test_regelspraak_ongedekt_begrip_waarschuwt(settings, store):
    """Een rapport-begrip dat het model niet dekt → dekking-waarschuwing in job.waarschuwingen, zonder
    de job te laten falen (de herkomst is aanwezig via vindplaatsen)."""
    eng = WetsanalyseEngine(settings, store, _RsOngedektLLM(), FakeWettenbank())
    job_id = await _tot_klaar(eng)
    await eng.run_regelspraak(job_id, review=True)  # stopt op het gegevens-checkpoint

    job = await store.load_job(job_id)
    assert job.state == JobState.wacht_review_rs_gegevens
    assert any("Begrip 'b1'" in w for w in job.waarschuwingen)


async def test_regelspraak_retry_hervat_rs_fase(settings, store):
    """Retry herkent de rs-fase via current_activiteit en hervat in de review-state (niet act-2)."""
    eng = WetsanalyseEngine(settings, store, _RsGeenHerkomstLLM(), FakeWettenbank())
    job_id = await _tot_klaar(eng)
    await eng.run_regelspraak(job_id, review=False)
    assert (await store.load_job(job_id)).state == JobState.fout

    await eng.retry(job_id)
    job = await store.load_job(job_id)
    assert job.state == JobState.wacht_review_rs_gegevens
    assert job.current_activiteit == "rs-gegevens"


async def test_regelspraak_akkoord_weigert_onbetrouwbaar_model(settings, store):
    """A4: een via retry hervatte, brongetrouwheid-falende ronde mag met 'akkoord' niet promoveren."""
    eng = WetsanalyseEngine(settings, store, _RsGeenHerkomstLLM(), FakeWettenbank())
    job_id = await _tot_klaar(eng)
    await eng.run_regelspraak(job_id, review=False)  # → fout (herkomst ontbreekt)
    await eng.retry(job_id)                           # → wacht_review_rs_gegevens
    assert (await store.load_job(job_id)).state == JobState.wacht_review_rs_gegevens

    await eng.apply_feedback(job_id, Feedback(status="akkoord", activiteit="rs-gegevens"))
    job = await store.load_job(job_id)
    # Promotie geweigerd: terug naar fout i.p.v. door naar de regels-stap.
    assert job.state == JobState.fout
    assert job.error.klasse == FoutKlasse.validatie


async def test_regelspraak_dubbele_claim_verliest(engine, store):
    """Tweede claim_regelspraak op dezelfde job geeft None (backt de 409 op een dubbele POST)."""
    job_id = await _tot_klaar(engine)
    eerste = await engine.claim_regelspraak(job_id, review=False)
    tweede = await engine.claim_regelspraak(job_id, review=False)
    assert eerste is not None
    assert tweede is None


async def test_regelspraak_rondecap(engine, store, settings):
    """De 6-rondencap forceert akkoord en promoveert; nooit een (max+1)-ronde."""
    job_id = await _tot_klaar(engine)
    await engine.run_regelspraak(job_id, review=True)
    assert (await store.load_job(job_id)).state == JobState.wacht_review_rs_gegevens

    for _ in range(settings.max_rondes):
        if (await store.load_job(job_id)).state != JobState.wacht_review_rs_gegevens:
            break
        await engine.apply_feedback(
            job_id,
            Feedback(status="wijzigingen", activiteit="rs-gegevens", items={"ot1": "Pas aan."}),
        )

    assert await store.hoogste_ronde(job_id, "rs-gegevens") <= settings.max_rondes
    # De cap heeft de GegevensSpraak afgesloten en doorgepromoveerd naar de regels-stap.
    assert (await store.load_job(job_id)).state == JobState.wacht_review_rs_regels


def test_merge_validatiepunten_union_en_ontdubbeling():
    """A2: een revise mag eerder genoteerde validatiepunten niet wegvegen — union met behoud van
    volgorde en ontdubbeling."""
    from app.engine.regelspraak_steps import _merge_validatiepunten

    assert _merge_validatiepunten(["a", "b"], ["b", "c"]) == ["a", "b", "c"]
    assert _merge_validatiepunten(["a"], []) == ["a"]          # revise herhaalt niets → oud behouden
    assert _merge_validatiepunten([], ["x"]) == ["x"]
    assert _merge_validatiepunten(["a", "a"], ["a"]) == ["a"]  # dedupe, eerste voorkomen wint
