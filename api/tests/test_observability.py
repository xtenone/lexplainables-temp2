"""Tests voor app/observability.py: JSON-formatter, secret-redactie, request-id-correlatie en de
no-op-shims (OTel niet vereist). Geen netwerk, geen OTLP-endpoint."""

from __future__ import annotations

import json
import logging

from app import observability as o


class _Settings:
    log_level = "info"
    log_format = "json"
    otel_endpoint = ""
    otel_service_name = "wetsanalyse-api"
    otel_metrics_enabled = True


def _record(**extra) -> logging.LogRecord:
    rec = logging.getLogger("app.test").makeRecord(
        "app.test", logging.INFO, "f.py", 1, "hallo", (), None
    )
    rec.__dict__.update(extra)
    return rec


def test_json_formatter_basisvorm():
    d = json.loads(o.JsonFormatter().format(_record(bwbId="BWBR1", categorie="audit")))
    assert d["niveau"] == "info"
    assert d["categorie"] == "audit"
    assert d["bericht"] == "hallo"
    assert d["logger"] == "app.test"
    assert d["bwbId"] == "BWBR1"
    # UTC-ISO-tijdstempel
    assert d["ts"].endswith("+00:00")


def test_json_formatter_redacteert_geheimen():
    d = json.loads(
        o.JsonFormatter().format(
            _record(token="geheim", secret="x", password="y", authorization="Bearer z", bwbId="BWBR1")
        )
    )
    for veld in ("token", "secret", "password", "authorization"):
        assert veld not in d
    assert d["bwbId"] == "BWBR1"


def test_json_formatter_neemt_geen_none_mee():
    d = json.loads(o.JsonFormatter().format(_record(leeg=None, gevuld=3)))
    assert "leeg" not in d
    assert d["gevuld"] == 3


def test_request_id_in_log():
    tok = o.request_id_var.set("req-123")
    try:
        d = json.loads(o.JsonFormatter().format(_record()))
    finally:
        o.request_id_var.reset(tok)
    assert d["request_id"] == "req-123"
    # Buiten een request geen request_id-veld.
    assert "request_id" not in json.loads(o.JsonFormatter().format(_record()))


def test_noop_tracer_en_meter():
    t = o.get_tracer("app.test")
    with t.start_as_current_span("s") as span:
        span.set_attribute("k", "v")
        span.record_exception(ValueError("x"))
    m = o.get_meter("app.test")
    m.create_counter("c").add(1)
    m.create_histogram("h").record(1.5)


def test_setup_zonder_endpoint_is_noop_otel():
    # setup() is idempotent en mag zonder endpoint niet crashen.
    o.setup(_Settings())
    o.setup(_Settings())
