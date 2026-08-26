"""Tests voor de FastAPI-service: legacy-vorm, batch, fouten, API-key.

``run_import``/``run_imports`` worden gemonkeypatcht — geen netwerk/GraphDB.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.service as service
from app.models import ImportResult, ImportSummary


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("BWB_SERVICE_API_KEY", raising=False)
    with TestClient(service.app) as test_client:
        yield test_client


def _summary(bwb_id: str) -> ImportSummary:
    return ImportSummary(bwb_id=bwb_id, wetten=1, artikelen=2)


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_enkele_import_behoudt_legacy_vorm(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(service, "run_import", lambda bwb_id, settings: _summary(bwb_id))
    resp = client.post("/import", json={"bwb_id": "BWBR0000001"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["overzicht"]["bwb_id"] == "BWBR0000001"
    assert "resultaten" not in body


def test_enkele_import_fout_geeft_500(client: TestClient, monkeypatch) -> None:
    def faal(bwb_id, settings):
        raise RuntimeError("boem")

    monkeypatch.setattr(service, "run_import", faal)
    resp = client.post("/import", json={"bwb_id": "BWBR0000001"})
    assert resp.status_code == 500
    assert "boem" in resp.json()["detail"]


def test_batch_import_happy_path(client: TestClient, monkeypatch) -> None:
    def batch(bwb_ids, settings):
        return [ImportResult(bwb_id=b, ok=True, overzicht=_summary(b)) for b in bwb_ids]

    monkeypatch.setattr(service, "run_imports", batch)
    resp = client.post("/import", json={"bwb_ids": ["BWBR0000001", "BWBR0000002"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert [r["bwb_id"] for r in body["resultaten"]] == ["BWBR0000001", "BWBR0000002"]
    assert all(r["status"] == "ok" for r in body["resultaten"])


def test_batch_import_gedeeltelijke_fout(client: TestClient, monkeypatch) -> None:
    def batch(bwb_ids, settings):
        return [
            ImportResult(bwb_id="BWBR0000001", ok=True, overzicht=_summary("BWBR0000001")),
            ImportResult(bwb_id="BWBR9999999", ok=False, fout="niet gevonden"),
        ]

    monkeypatch.setattr(service, "run_imports", batch)
    resp = client.post("/import", json={"bwb_ids": ["BWBR0000001", "BWBR9999999"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "gedeeltelijk"
    fout = body["resultaten"][1]
    assert fout["status"] == "fout"
    assert fout["fout"] == "niet gevonden"
    assert fout["overzicht"] is None


def test_batch_import_alles_mislukt(client: TestClient, monkeypatch) -> None:
    def batch(bwb_ids, settings):
        return [ImportResult(bwb_id=b, ok=False, fout="x") for b in bwb_ids]

    monkeypatch.setattr(service, "run_imports", batch)
    resp = client.post("/import", json={"bwb_ids": ["BWBR0000001"]})
    assert resp.json()["status"] == "mislukt"


def test_lege_bwb_ids_geeft_422(client: TestClient) -> None:
    assert client.post("/import", json={"bwb_ids": []}).status_code == 422


def test_api_key_vereist_indien_geconfigureerd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BWB_SERVICE_API_KEY", "geheim")
    with TestClient(service.app) as client_met_key:
        assert client_met_key.post("/import", json={"bwb_id": "X"}).status_code == 401
        monkeypatch.setattr(service, "run_import", lambda bwb_id, settings: _summary(bwb_id))
        resp = client_met_key.post("/import", json={"bwb_id": "X"}, headers={"X-API-Key": "geheim"})
        assert resp.status_code == 200


def test_run_imports_loopt_door_na_fout(monkeypatch: pytest.MonkeyPatch) -> None:
    """De batch-runner vangt per wet exceptions en gaat verder."""
    import app.main as main_module

    monkeypatch.setattr(main_module, "maak_writer", lambda settings: object())
    monkeypatch.setattr(main_module, "prepare", lambda writer: None)

    def nep_import(bwb_id, settings, writer=None):
        if bwb_id == "SLECHT":
            raise RuntimeError("kapot")
        return _summary(bwb_id)

    monkeypatch.setattr(main_module, "run_import", nep_import)
    resultaten = main_module.run_imports(["GOED", "SLECHT", "OOK_GOED"], settings=None)
    assert [r.ok for r in resultaten] == [True, False, True]
    assert resultaten[1].fout == "kapot"
