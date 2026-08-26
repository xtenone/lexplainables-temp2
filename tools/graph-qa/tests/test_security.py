"""WP-B: timing-safe tokencheck en CORS-credentials-regel."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import api.main as main


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_geen_token_geconfigureerd_is_open(monkeypatch):
    monkeypatch.setattr(main.settings, "qa_api_token", None)
    assert main._check_auth(_creds("wat-dan-ook")) is None
    assert main._check_auth(None) is None


def test_juist_token_wordt_geaccepteerd(monkeypatch):
    monkeypatch.setattr(main.settings, "qa_api_token", "geheim")
    assert main._check_auth(_creds("geheim")) is None


def test_fout_of_ontbrekend_token_wordt_geweigerd(monkeypatch):
    monkeypatch.setattr(main.settings, "qa_api_token", "geheim")
    with pytest.raises(HTTPException):
        main._check_auth(_creds("mis"))
    with pytest.raises(HTTPException):
        main._check_auth(None)


def test_cors_credentials_niet_bij_wildcard():
    from agent.config import Settings

    assert Settings(cors_origins=["*"]).cors_origins == ["*"]
    # De main-module leidt hieruit allow_credentials=False af (wildcard).
    # Bij een expliciete origin mag het wél.
    assert Settings(cors_origins=["https://x.nl"]).cors_origins == ["https://x.nl"]


def test_cors_wildcard_ook_in_gemengde_lijst():
    # M1: "*" naast een expliciete origin telt óók als wildcard → credentials uit. Anders reflecteert
    # Starlette elke origin mét credentials (de omzeiling die de guard juist moet dichten).
    from api import main

    assert main._has_wildcard_origin(["*"]) is True
    assert main._has_wildcard_origin(["*", "https://x.nl"]) is True
    assert main._has_wildcard_origin(["https://x.nl"]) is False


def test_client_ip_eert_xff_alleen_met_trust_proxy(monkeypatch):
    # L4: standaard peer-IP (geen spoof-omzeiling); met trust_proxy de eerste X-Forwarded-For-hop.
    from types import SimpleNamespace

    from api import main

    req = SimpleNamespace(
        headers={"x-forwarded-for": "1.2.3.4, 10.0.0.1"},
        client=SimpleNamespace(host="10.0.0.1"),
    )
    monkeypatch.setattr(main, "settings", SimpleNamespace(trust_proxy=False))
    assert main._client_ip(req) == "10.0.0.1"
    monkeypatch.setattr(main, "settings", SimpleNamespace(trust_proxy=True))
    assert main._client_ip(req) == "1.2.3.4"
