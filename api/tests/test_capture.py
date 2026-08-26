"""Tests voor het vastleggen van LLM-calls (prompt + ruwe respons) voor analyse.

Dekt: de store-roundtrip (llm_calls + app_settings), de CapturingLLMClient (aan/uit/exception,
best-effort) en een integratierun waarin een echte analyse meerdere calls vastlegt.
"""

import pytest

from app import app_settings
from app.contracts import BronInput, StartRequest
from app.llm.base import LLMError, LLMResult
from app.llm.capture import CapturingLLMClient, gebruik_context


@pytest.fixture(autouse=True)
def _schone_cache():
    """De app_settings-cache is procesglobaal; leeg 'm rond elke test tegen lekkage."""
    app_settings._wis_cache()
    yield
    app_settings._wis_cache()


class _VasteLLM:
    """Minimale inner-client die een vaste respons teruggeeft."""

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, system, user, schema=None):
        self.calls += 1
        return LLMResult(data={"ok": True}, model="m", provider="p",
                         tokens_in=11, tokens_out=22, ruwe_tekst='{"ok": true}')


class _FoutLLM:
    async def complete(self, system, user, schema=None):
        raise LLMError("boem")


# --- store-roundtrip ----------------------------------------------------------

async def test_store_llm_call_roundtrip(store):
    await store.schrijf_llm_call({
        "project_slug": "p1", "activiteit": "2", "ronde": 1, "poging": 1, "fase": "generatie",
        "model": "m", "provider": "p", "system_prompt": "sys", "user_prompt": "usr",
        "response_text": "resp", "tokens_in": 5, "tokens_out": 6, "ok": True,
    })
    rijen = await store.lijst_llm_calls("p1")
    assert len(rijen) == 1
    assert rijen[0]["system_prompt"] == "sys" and rijen[0]["response_text"] == "resp"
    assert await store.lijst_llm_calls("ander") == []


async def test_store_app_setting_roundtrip(store):
    assert await store.lees_app_setting("capture_llm_calls") is None
    await store.schrijf_app_setting("capture_llm_calls", True)
    assert await store.lees_app_setting("capture_llm_calls") is True
    await store.schrijf_app_setting("capture_llm_calls", False)  # upsert
    assert await store.lees_app_setting("capture_llm_calls") is False


# --- CapturingLLMClient -------------------------------------------------------

async def test_capture_uit_legt_niets_vast(store):
    client = CapturingLLMClient(_VasteLLM(), store)
    with gebruik_context(project_slug="p1", activiteit="2", ronde=1):
        await client.complete("sys", "usr")
    assert await store.lijst_llm_calls("p1") == []


async def test_capture_aan_legt_prompt_en_respons_vast(store):
    await app_settings.set_capture(store, True)
    client = CapturingLLMClient(_VasteLLM(), store)
    with gebruik_context(project_slug="p1", activiteit="3", ronde=2, poging=1, fase="generatie"):
        await client.complete("system-prompt", "user-prompt")
    rijen = await store.lijst_llm_calls("p1")
    assert len(rijen) == 1
    r = rijen[0]
    assert r["system_prompt"] == "system-prompt" and r["user_prompt"] == "user-prompt"
    assert r["response_text"] == '{"ok": true}'
    assert r["activiteit"] == "3" and r["ronde"] == 2 and r["fase"] == "generatie"
    assert r["tokens_in"] == 11 and r["tokens_out"] == 22 and r["ok"] is True


async def test_capture_legt_gefaalde_call_vast_en_reraiset(store):
    await app_settings.set_capture(store, True)
    client = CapturingLLMClient(_FoutLLM(), store)
    with gebruik_context(project_slug="p1", activiteit="2", ronde=1):
        with pytest.raises(LLMError):
            await client.complete("sys", "usr")
    rijen = await store.lijst_llm_calls("p1")
    assert len(rijen) == 1 and rijen[0]["ok"] is False
    assert "boem" in (rijen[0]["error"] or "")


# --- integratie ---------------------------------------------------------------

async def test_integratie_analyse_legt_meerdere_calls_vast(engine, store):
    await app_settings.set_capture(store, True)
    job = await engine.create_job(
        StartRequest(bronnen=[BronInput(bwbId="BWBR9999999", artikel="1")], review=False), "test"
    )
    await engine.run_initial(job.id)

    rijen = await store.lijst_llm_calls(job.id)
    # Minstens: act-2 inventaris + act-2 generatie + act-3 generatie.
    assert len(rijen) >= 3
    activiteiten = {r["activiteit"] for r in rijen}
    assert "2" in activiteiten and "3" in activiteiten
    assert any(r["fase"] == "inventaris" for r in rijen)
    assert all(r["system_prompt"] and r["user_prompt"] for r in rijen)
