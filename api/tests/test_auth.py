import pytest
from fastapi import HTTPException

from app.auth import authenticate
from app.config import Settings


def _settings_met_tokens(raw: str) -> Settings:
    s = Settings()
    s.client_tokens = {}
    for part in raw.split(","):
        cid, tok = part.split(":", 1)
        s.client_tokens[tok] = cid
    s.auth_required = True
    return s


def test_geldig_token_geeft_client_id():
    s = _settings_met_tokens("belasting:geheim123")
    assert authenticate("Bearer geheim123", s) == "belasting"


def test_ontbrekend_token_401():
    s = _settings_met_tokens("belasting:geheim123")
    with pytest.raises(HTTPException) as e:
        authenticate(None, s)
    assert e.value.status_code == 401


def test_fout_token_401():
    s = _settings_met_tokens("belasting:geheim123")
    with pytest.raises(HTTPException):
        authenticate("Bearer mis", s)


def test_fail_closed_zonder_tokens():
    s = Settings()
    s.client_tokens = {}
    s.auth_required = True
    with pytest.raises(HTTPException):
        authenticate("Bearer wat-dan-ook", s)
