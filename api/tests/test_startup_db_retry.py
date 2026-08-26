"""De startup DB-connect-retry (`app.main._init_db_met_retry`): bij een nog-niet-klare DB retrye we
met bounded backoff i.p.v. crash-loopen (postgres draait als aparte stack, geen cross-stack
depends_on). Geen netwerk/DB — `create_all`/`reconcile_schema`/`sleep` worden gemockt."""

from __future__ import annotations

import pytest
import sqlalchemy.exc


def _op_error() -> sqlalchemy.exc.OperationalError:
    return sqlalchemy.exc.OperationalError("SELECT 1", {}, Exception("connection refused"))


async def test_db_retry_slaagt_na_paar_pogingen(monkeypatch):
    monkeypatch.setenv("WETSANALYSE_DB_CONNECT_RETRIES", "5")
    monkeypatch.setenv("WETSANALYSE_DB_CONNECT_BACKOFF", "0")
    from app import main

    calls = {"create": 0, "reconcile": 0, "sleep": 0}

    async def flaky_create_all():
        calls["create"] += 1
        if calls["create"] < 3:  # eerste twee pogingen mislukken
            raise _op_error()

    async def ok_reconcile():
        calls["reconcile"] += 1

    async def fake_sleep(_s):
        calls["sleep"] += 1

    monkeypatch.setattr(main.db, "create_all", flaky_create_all)
    monkeypatch.setattr(main.db, "reconcile_schema", ok_reconcile)
    monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)

    await main._init_db_met_retry()

    assert calls["create"] == 3  # 2 mislukt + 1 gelukt
    assert calls["reconcile"] == 1  # pas na een geslaagde create_all
    assert calls["sleep"] == 2  # één backoff per mislukking


async def test_db_retry_geeft_op_na_max(monkeypatch):
    monkeypatch.setenv("WETSANALYSE_DB_CONNECT_RETRIES", "3")
    monkeypatch.setenv("WETSANALYSE_DB_CONNECT_BACKOFF", "0")
    from app import main

    async def altijd_stuk():
        raise _op_error()

    async def noop_sleep(_s):
        return None

    monkeypatch.setattr(main.db, "create_all", altijd_stuk)
    monkeypatch.setattr(main.asyncio, "sleep", noop_sleep)

    with pytest.raises(sqlalchemy.exc.OperationalError):
        await main._init_db_met_retry()
