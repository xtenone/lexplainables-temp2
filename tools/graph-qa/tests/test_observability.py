"""PR 2.1: observability is fail-open en gated (no-op zonder endpoint/otel-extra)."""
from __future__ import annotations

import json
import logging

from agent import observability
from agent.config import Settings


def test_jsonformatter_emit_geldige_json_met_kernvelden():
    rec = logging.makeLogRecord({"msg": "hallo", "name": "test"})
    out = observability.JsonFormatter().format(rec)
    data = json.loads(out)
    assert data["bericht"] == "hallo"
    assert data["logger"] == "test"
    assert data["niveau"] == "info"
    assert "ts" in data


def test_jsonformatter_redacteert_geheime_velden():
    rec = logging.makeLogRecord({"msg": "x", "token": "geheim", "question": "prive"})
    data = json.loads(observability.JsonFormatter().format(rec))
    assert "token" not in data
    assert "question" not in data  # promptinhoud wordt niet gelogd


def test_setup_otel_is_noop_zonder_endpoint():
    # Geen endpoint → geen exception, geen OTel.
    observability._setup_otel(Settings(otel_endpoint=""))


def test_get_tracer_geeft_bruikbare_span_zonder_otel_extra():
    tracer = observability.get_tracer("test")
    with tracer.start_as_current_span("s") as span:
        span.set_attribute("k", "v")  # mag niet omvallen zonder otel-extra
