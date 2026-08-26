"""De startup DB-connect-retry (`app.main._wacht_op_db`): bij een nog-niet-klare DB retrye we met
bounded backoff i.p.v. crash-loopen (postgres draait als aparte stack, geen cross-stack
depends_on). Geen netwerk/DB — de connectie en `sleep` worden gemockt. Sinds werkwijze-ADR-0005
beheert deze functie geen schema meer (dat is Alembic's taak) — ze wacht alleen tot de DB een
simpele query beantwoordt."""

from __future__ import annotations

import pytest
import sqlalchemy.exc


def _op_error() -> sqlalchemy.exc.OperationalError:
    return sqlalchemy.exc.OperationalError("SELECT 1", {}, Exception("connection refused"))


class _FakeConn:
    def __init__(self, calls: dict, faal_tot: int) -> None:
        self._calls = calls
        self._faal_tot = faal_tot

    async def __aenter__(self):
        self._calls["connect"] += 1
        if self._calls["connect"] <= self._faal_tot:
            raise _op_error()
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, _stmt):
        return None


class _FakeEngine:
    """`engine.connect()` retourneert een async context manager, net als SQLAlchemy's AsyncEngine."""

    def __init__(self, faal_tot: int = 0) -> None:
        self.calls = {"connect": 0}
        self._faal_tot = faal_tot

    def connect(self):
        return _FakeConn(self.calls, self._faal_tot)


async def test_db_retry_slaagt_na_paar_pogingen(monkeypatch):
    monkeypatch.setenv("WETSANALYSE_DB_CONNECT_RETRIES", "5")
    monkeypatch.setenv("WETSANALYSE_DB_CONNECT_BACKOFF", "0")
    from app import main

    calls = {"sleep": 0}

    async def fake_sleep(_s):
        calls["sleep"] += 1

    monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)

    engine = _FakeEngine(faal_tot=2)  # eerste twee pogingen mislukken
    await main._wacht_op_db(engine)

    assert engine.calls["connect"] == 3  # 2 mislukt + 1 gelukt
    assert calls["sleep"] == 2  # één backoff per mislukking


async def test_db_retry_geeft_op_na_max(monkeypatch):
    monkeypatch.setenv("WETSANALYSE_DB_CONNECT_RETRIES", "3")
    monkeypatch.setenv("WETSANALYSE_DB_CONNECT_BACKOFF", "0")
    from app import main

    async def noop_sleep(_s):
        return None

    monkeypatch.setattr(main.asyncio, "sleep", noop_sleep)

    engine = _FakeEngine(faal_tot=10**6)  # altijd stuk

    with pytest.raises(sqlalchemy.exc.OperationalError):
        await main._wacht_op_db(engine)
