"""LLM-kostenrem: globale concurrency-limiter (throttle) + slimmere transient-retry (Retry-After)
+ de pre-flight prompt-token-guard en de afgeslankte act-3-prompt (context-window)."""

import asyncio

import pytest

from app.engine.retry import is_transient, met_retry, retry_after_seconds
from app.llm import throttle


# --- #1 concurrency-limiter ---

async def test_llm_slot_begrenst_gelijktijdigheid():
    throttle.configure(2)
    try:
        actief = piek = 0

        async def taak():
            nonlocal actief, piek
            async with throttle.llm_slot():
                actief += 1
                piek = max(piek, actief)
                await asyncio.sleep(0.01)
                actief -= 1

        await asyncio.gather(*(taak() for _ in range(6)))
        assert piek <= 2  # nooit meer dan het plafond tegelijk
    finally:
        throttle.configure(0)


async def test_llm_slot_uit_is_noop():
    throttle.configure(0)
    async with throttle.llm_slot():
        pass  # geen rem, geen blokkade


# --- #2 Retry-After ---

def test_retry_after_uit_attribuut():
    class E(Exception):
        retry_after = 7

    assert retry_after_seconds(E()) == 7.0


def test_retry_after_uit_header():
    class Resp:
        headers = {"retry-after": "12"}

    class E(Exception):
        response = Resp()

    assert retry_after_seconds(E()) == 12.0


def test_retry_after_afwezig():
    assert retry_after_seconds(Exception("geen hint")) is None


async def test_met_retry_honoreert_retry_after(monkeypatch):
    import app.engine.retry as r

    slaapjes: list[float] = []

    async def fake_sleep(s):
        slaapjes.append(s)

    monkeypatch.setattr(r.asyncio, "sleep", fake_sleep)

    class RateLimitError(Exception):  # naam telt als transiënt (is_transient)
        retry_after = 5

    pogingen = {"n": 0}

    async def maak():
        pogingen["n"] += 1
        if pogingen["n"] == 1:
            raise RateLimitError()
        return "ok"

    res = await met_retry(maak, max_retries=3, backoff=0.5, max_backoff=30)
    assert res == "ok" and pogingen["n"] == 2
    # Wachttijd op basis van Retry-After (5s) + jitter ≤ 25%, niet de 0.5s backoff.
    assert 5.0 <= slaapjes[0] <= 6.25


async def test_met_retry_plafonneert_backoff(monkeypatch):
    import app.engine.retry as r

    slaapjes: list[float] = []

    async def fake_sleep(s):
        slaapjes.append(s)

    monkeypatch.setattr(r.asyncio, "sleep", fake_sleep)

    class RateLimitError(Exception):
        pass

    async def maak():
        raise RateLimitError()

    try:
        await met_retry(maak, max_retries=3, backoff=100, max_backoff=10)
    except RateLimitError:
        pass
    # Exponentiële backoff (100, 200, …) wordt geplafonneerd op 10 + max 25% jitter.
    assert all(s <= 12.5 for s in slaapjes)


# --- #3 context-window: act-3-prompts + pre-flight token-guard ---

def test_act3_prompts_dragen_ledentekst_en_markeringen():
    """Act-3 krijgt bewust de volledige leden-tekst mee (definities dicht op de bron); het
    context-window-risico wordt door de prompt-token-guard gevangen, niet door trimmen."""
    from app.engine.prompts import act3_begrippen_prompt, act3_regels_prompt

    context = {
        "werkgebied": {"naam": "WG"},
        "bronnen": [{
            "bron_id": "br1", "label": "Wet X art. 1", "bwbId": "BWBR1", "artikel": "1",
            "leden": [{"lid": "1", "tekst": "UNIEKE_LEDEN_TEKST_XYZ voedt de definities"}],
            "markeringen": [
                {"id": "m1", "bron_id": "br1", "formulering": "MARKERING_ABC",
                 "klasse": "Rechtssubject", "vindplaats": "lid 1"},
                {"id": "m2", "bron_id": "br1", "formulering": "REGEL_MARKERING_DEF",
                 "klasse": "Afleidingsregel", "vindplaats": "lid 1"},
            ],
            "verwijzingen": [],
        }],
    }
    _system, user, _schema, _h = act3_begrippen_prompt(context)
    assert "UNIEKE_LEDEN_TEKST_XYZ" in user       # leden-tekst gaat mee
    assert "MARKERING_ABC" in user                # markeringen blijven de basis
    assert "br1" in user                          # bron-index aanwezig voor vindplaatsen

    begrippen = [{"id": "b1", "naam": "x", "klasse": "Rechtssubject", "definitie": "d"}]
    _system, user, _schema, _h = act3_regels_prompt(context, begrippen)
    assert "UNIEKE_LEDEN_TEKST_XYZ" in user       # ook 3b ziet de wettekst
    assert "REGEL_MARKERING_DEF" in user          # regel-relevante markering gaat mee
    assert "MARKERING_ABC" not in user            # niet-regel-relevante klasse is eruit gefilterd
    assert '"b1"' in user                         # de 3a-begrippen zijn de bouwstenen


def test_prompt_guard_werpt_bij_overschrijding():
    from app.llm.base import LlmConfig, PromptTooLargeError
    from app.llm.litellm_client import LiteLLMClient

    client = LiteLLMClient(LlmConfig(model="gpt-test", max_prompt_tokens=10))
    with pytest.raises(PromptTooLargeError):
        # ~250 tokens via de chars/4-fallback ≫ cap 10.
        client._guard_prompt([{"role": "user", "content": "x" * 1000}])


def test_prompt_guard_laat_klein_door_en_noop_zonder_limiet():
    from app.llm.base import LlmConfig
    from app.llm.litellm_client import LiteLLMClient

    # Onder de cap → geen fout.
    LiteLLMClient(LlmConfig(model="gpt-test", max_prompt_tokens=100000))._guard_prompt(
        [{"role": "user", "content": "kort"}]
    )
    # Geen cap + onbekend model → geen afleidbare limiet → geen fout, ongeacht grootte.
    LiteLLMClient(LlmConfig(model="onbekend-model-zzz", max_prompt_tokens=0))._guard_prompt(
        [{"role": "user", "content": "x" * 100000}]
    )


def test_prompt_too_large_niet_transient():
    from app.llm.base import PromptTooLargeError

    # Niet-transiënt → wordt door met_retry niet 5× herhaald.
    assert is_transient(PromptTooLargeError("te groot")) is False


def test_is_transient_op_http_status():
    """Naast de klassenaam-set herkent is_transient ook een HTTP-status op de fout of de response
    (robuust bij LiteLLM-versiewissels / doorgelekte httpx-fouten)."""

    class VreemdeFout(Exception):
        def __init__(self, status):
            self.status_code = status

    class MetResponse(Exception):
        def __init__(self, status):
            self.response = type("R", (), {"status_code": status})()

    assert is_transient(VreemdeFout(429)) is True
    assert is_transient(VreemdeFout(503)) is True
    assert is_transient(MetResponse(502)) is True
    assert is_transient(VreemdeFout(400)) is False   # client-fout: niet retryen
    assert is_transient(Exception("gewone fout zonder status")) is False


# --- #4 MCP-foutklasse: client-fouten (niet-bestaand artikel) niet retryen ---

def test_wettenbank_client_fout_niet_transient():
    from app.wettenbank import WettenbankError

    assert is_transient(WettenbankError("artikel niet gevonden", klasse="client")) is False
    assert is_transient(WettenbankError("regeling bestaat niet", klasse="permanent")) is False
    # Zonder klasse (transportfout) of met transiënte klasse blijft retryen het gedrag.
    assert is_transient(WettenbankError("fetch failed")) is True
    assert is_transient(WettenbankError("SRU 503", klasse="transient")) is True


async def test_met_retry_stopt_direct_op_client_fout(monkeypatch):
    import app.engine.retry as r
    from app.wettenbank import WettenbankError

    monkeypatch.setattr(r.asyncio, "sleep", lambda s: pytest.fail("mag niet slapen"))
    pogingen = 0

    async def maak():
        nonlocal pogingen
        pogingen += 1
        raise WettenbankError("Artikel 999 niet gevonden", klasse="client")

    with pytest.raises(WettenbankError):
        await met_retry(maak, max_retries=3, backoff=0.1)
    assert pogingen == 1  # geen backoff-loop op een permanente client-fout


def test_parse_zet_foutklasse_op_wettenbank_error():
    """De MCP stuurt de fout als JSON {"fout","foutCode","klasse"} in het text-block;
    _parse moet de klasse op de exceptie zetten (best-effort: geen JSON → None)."""
    import json

    from app.wettenbank import WettenbankClient, WettenbankError

    class Block:
        type = "text"

        def __init__(self, text: str) -> None:
            self.text = text

    class Result:
        is_error = True

        def __init__(self, text: str) -> None:
            self.content = [Block(text)]

    payload = json.dumps({"fout": "Artikel 999 niet gevonden", "foutCode": "ARTIKEL_NIET_GEVONDEN", "klasse": "client"})
    with pytest.raises(WettenbankError) as ei:
        WettenbankClient._parse("wettenbank_artikel", Result(payload))
    assert ei.value.klasse == "client"
    assert "Artikel 999 niet gevonden" in str(ei.value)

    with pytest.raises(WettenbankError) as ei:
        WettenbankClient._parse("wettenbank_artikel", Result("kale foutmelding, geen JSON"))
    assert ei.value.klasse is None


# --- usage-telling over de repareer-retry heen -------------------------------

async def test_repair_retry_telt_usage_van_beide_calls(monkeypatch):
    """Faalt de eerste generatie op JSON en herstelt de repareer-retry het, dan telt de
    LLMResult de tokens van BEIDE calls — de eerste (mislukte) generatie is óók verbruik.

    litellm zit in de optionele `llm`-extra en ontbreekt in de CI-testomgeving; de client
    importeert het pas ín complete(), dus een stub-module in sys.modules volstaat en de test
    draait overal (de token-fallback vangt het ontbrekende token_counter-attribuut op)."""
    import sys
    import types

    from app.llm.base import LlmConfig
    from app.llm.litellm_client import LiteLLMClient

    class _Usage:
        def __init__(self, i, o):
            self.prompt_tokens = i
            self.completion_tokens = o

    class _Msg:
        def __init__(self, c):
            self.content = c

    class _Choice:
        def __init__(self, c):
            self.message = _Msg(c)

    class _Resp:
        def __init__(self, c, i, o):
            self.choices = [_Choice(c)]
            self.usage = _Usage(i, o)
            self.model = "fake/model"

    responsen = iter([
        _Resp("dit is geen json", 10, 5),          # eerste poging: onparseerbaar
        _Resp('{"ok": true}', 20, 7),              # repareer-retry: geldig
    ])

    async def fake_acompletion(**kwargs):
        return next(responsen)

    stub = types.ModuleType("litellm")
    stub.acompletion = fake_acompletion
    monkeypatch.setitem(sys.modules, "litellm", stub)
    client = LiteLLMClient(LlmConfig(model="fake/model", max_prompt_tokens=1_000_000))
    res = await client.complete("sys", "user")

    assert res.data == {"ok": True}
    assert res.tokens_in == 30   # 10 + 20
    assert res.tokens_out == 12  # 5 + 7


# --- #4 prompt caching: cachebaar system-blok + cache-token-telemetrie ---

def test_system_message_cachebaar_blok_aan_en_uit():
    from app.llm.base import LlmConfig
    from app.llm.litellm_client import LiteLLMClient

    aan = LiteLLMClient(LlmConfig(model="m", prompt_caching=True))._system_message("REF")
    assert aan["content"] == [{"type": "text", "text": "REF", "cache_control": {"type": "ephemeral"}}]

    uit = LiteLLMClient(LlmConfig(model="m", prompt_caching=False))._system_message("REF")
    assert uit == {"role": "system", "content": "REF"}


def test_cache_tokens_leest_usage_defensief():
    from app.llm.litellm_client import LiteLLMClient

    class Usage:  # provider-stijl usage-object
        cache_read_input_tokens = 1200
        cache_creation_input_tokens = 800

    assert LiteLLMClient._cache_tokens(Usage()) == (1200, 800)
    assert LiteLLMClient._cache_tokens(None) == (0, 0)

    class Nested:  # alternatieve vorm: genest onder prompt_tokens_details
        cache_read_input_tokens = 0
        cache_creation_input_tokens = 0
        class prompt_tokens_details:  # noqa: N801
            cached_tokens = 512

    assert LiteLLMClient._cache_tokens(Nested()) == (512, 0)


def test_references_in_system_niet_in_user():
    """Caching-invariant: de (grote, stabiele) references staan in het cachebare system-blok,
    de volatile per-call data in de user-prompt."""
    from app.engine.prompts import act2_prompt, act3_begrippen_prompt

    basis = {"wet": "Wet X", "bwbId": "BWBR1", "artikel": "1",
             "leden": [{"lid": "1", "tekst": "de minister stelt vast"}]}
    system, user, _schema, _h = act2_prompt(basis, None)
    assert "JAS-klassen" in system and "verwijzingen volgen" in system
    assert "REFERENTIE" not in user

    ctx = {"werkgebied": {"naam": "WG"}, "bronnen": [{"bron_id": "br1", "label": "L",
            "markeringen": [], "verwijzingen": []}]}
    system3, user3, _s3, _h3 = act3_begrippen_prompt(ctx)
    assert "begrippen en afleidingsregels" in system3
    assert "REFERENTIE" not in user3
