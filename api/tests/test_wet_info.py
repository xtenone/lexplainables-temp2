"""Wetsstructuur- en artikelinfo-endpoints (artikel-autocomplete + lid-keuze in de UI)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app import wet_info
from app.wet_info import _plat, _snippet
from app.wettenbank import WettenbankError

STRUCTUUR_DATA = {
    "bwbId": "BWBR9999999",
    "citeertitel": "Testwet",
    "versiedatum": "2026-01-01",
    "structuur": [
        {
            "type": "hoofdstuk", "nr": "1", "titel": "Algemene bepalingen",
            "artikelen": ["1", "2"],
            "secties": [
                {"type": "paragraaf", "nr": "1.1", "artikelen": ["3"]},
            ],
        },
        {"type": "hoofdstuk", "nr": "2", "artikelen": ["4"]},
    ],
}

ARTIKEL_DATA = {
    "bwbId": "BWBR9999999",
    "artikel": "3",
    "citeertitel": "Testwet",
    "sectie": "Artikel 3. Begripsbepalingen",
    "pad": "Hoofdstuk 1 > § 1.1 > Artikel 3",
    "leden": [
        {"lid": "1", "tekst": "In deze wet wordt verstaan onder aangifte: de opgave van gegevens."},
        {"lid": "2", "tekst": "Bij ministeriële regeling kunnen nadere regels worden gesteld."},
        {"lid": "", "tekst": "Ongenummerd lid dat geen keuze mag worden."},
    ],
}


class FakeStructuurWettenbank:
    def __init__(self, structuur=None, artikel=None, fout: Exception | None = None) -> None:
        self._structuur = structuur or STRUCTUUR_DATA
        self._artikel = artikel or ARTIKEL_DATA
        self.fout = fout
        self.calls = 0

    async def structuur(self, bwb_id: str) -> dict:
        self.calls += 1
        if self.fout:
            raise self.fout
        return self._structuur

    async def artikel(self, bwb_id: str, artikel: str, lid=None) -> dict:
        self.calls += 1
        if self.fout:
            raise self.fout
        return self._artikel


# --- _plat: boom → platte artikellijst -------------------------------------------

def test_plat_padopbouw_en_documentvolgorde():
    plat = _plat(STRUCTUUR_DATA["structuur"])
    assert [p["artikel"] for p in plat] == ["1", "2", "3", "4"]
    # Titel wint als label; zonder titel valt het segment terug op "{Type} {nr}".
    assert plat[0]["pad"] == "Algemene bepalingen"
    assert plat[2]["pad"] == "Algemene bepalingen › Paragraaf 1.1"
    assert plat[3]["pad"] == "Hoofdstuk 2"


def test_plat_platte_fallback_zonder_pad():
    # De MCP-fallback voor wetten zonder containers: één node {type:"wet", nr:""}.
    plat = _plat([{"type": "wet", "nr": "", "artikelen": ["1", "2"]}])
    assert plat == [{"artikel": "1", "pad": ""}, {"artikel": "2", "pad": ""}]


def test_snippet_kapt_op_woordgrens():
    assert _snippet("kort") == "kort"
    lang = _snippet("woord " * 100)
    assert len(lang) <= wet_info._SNIPPET_LEN + 1 and lang.endswith("…")
    assert not lang.rstrip("…").endswith(" ")  # geen half woord/spatie voor de ellipsis


# --- routes -----------------------------------------------------------------------

@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setenv("WETSANALYSE_AUTH_REQUIRED", "0")

    from app import db, ratelimit
    from app.config import get_settings
    from app.deps import get_store, get_wettenbank
    get_settings.cache_clear()
    get_store.cache_clear()
    get_wettenbank.cache_clear()
    ratelimit.reset()
    wet_info._wis_cache()

    db.init_engine("sqlite+aiosqlite://")
    await db.create_all()

    from app.main import app
    fake = FakeStructuurWettenbank()
    app.dependency_overrides[get_wettenbank] = lambda: fake
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        ac.fake = fake
        yield ac

    app.dependency_overrides.pop(get_wettenbank, None)
    get_settings.cache_clear()
    get_store.cache_clear()
    get_wettenbank.cache_clear()
    wet_info._wis_cache()
    await db.dispose_engine()


async def test_structuur_route_geeft_platte_lijst(client):
    r = await client.get("/v1/wetten/BWBR9999999/structuur")
    assert r.status_code == 200
    body = r.json()
    assert body["citeertitel"] == "Testwet"
    assert body["artikelen"][2] == {"artikel": "3", "pad": "Algemene bepalingen › Paragraaf 1.1"}


async def test_structuur_route_cachet(client):
    await client.get("/v1/wetten/BWBR9999999/structuur")
    n = client.fake.calls
    await client.get("/v1/wetten/BWBR9999999/structuur")
    assert client.fake.calls == n  # tweede request komt uit de TTL-cache


async def test_artikel_info_route(client):
    r = await client.get("/v1/wetten/BWBR9999999/artikelen/3")
    assert r.status_code == 200
    body = r.json()
    assert body["leden"] == ["1", "2"]  # ongenummerd lid weggefilterd
    assert body["opschrift"] == "Artikel 3. Begripsbepalingen"
    assert body["snippet"].startswith("In deze wet wordt verstaan")
    # leden_teksten draagt de VOLLEDIGE tekst (voor de annotatie-workbench), incl. het ongenummerde lid.
    assert len(body["leden_teksten"]) == 3
    assert body["leden_teksten"][0] == {
        "lid": "1",
        "tekst": "In deze wet wordt verstaan onder aangifte: de opgave van gegevens.",
    }


async def test_client_fout_wordt_404(client):
    client.fake.fout = WettenbankError("Artikel 999 niet gevonden in BWBR9999999", klasse="client")
    r = await client.get("/v1/wetten/BWBR9999999/artikelen/999")
    assert r.status_code == 404
    assert "999" in r.json()["detail"]  # de actionable MCP-melding gaat mee


async def test_transportfout_wordt_503_en_niet_gecachet(client):
    client.fake.fout = WettenbankError("MCP-timeout op wettenbank_structuur na 30s")
    assert (await client.get("/v1/wetten/BWBR9999999/structuur")).status_code == 503
    # Herstelde upstream → direct weer data (fouten worden niet gecachet).
    client.fake.fout = None
    assert (await client.get("/v1/wetten/BWBR9999999/structuur")).status_code == 200
