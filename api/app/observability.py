"""Centrale observability voor de Wetsanalyse-API: gestructureerde logging + OpenTelemetry.

Twee lagen, allebei fail-open (mogen de app nooit killen):

1. **Gestructureerde logging** — één JSON-regel per gebeurtenis naar stdout, gespiegeld aan de
   MCP-logger (`tools/wettenbank-mcp/src/logger.ts`): velden `ts` (UTC-ISO), `niveau`, `categorie`
   (`functioneel|audit|security`), `bericht`, plus vrije velden en — indien een OTel-span actief is —
   `trace_id`/`span_id`. Geheime velden worden geredacteerd (defence-in-depth). Werkt **zonder**
   dat `opentelemetry` geïnstalleerd is.

2. **OpenTelemetry** (traces + metrics + logs) — alleen actief als `OTEL_EXPORTER_OTLP_ENDPOINT`
   gezet is én de `otel`-extra geïnstalleerd. Anders volledig no-op: `get_tracer()`/`get_meter()`
   geven veilige no-op-objecten terug, zodat de rest van de app onvoorwaardelijk spans/metrics mag
   aanmaken.

Normenkader (gelijk aan de MCP): BIO2 / NEN-EN-ISO/IEC 27002:2022 — 8.15 Logging, 8.16 Monitoring
(auth/security apart herkenbaar via `categorie`), 8.17 Clock synchronisation (UTC/ISO-8601).
AVG/dataminimalisatie: tokens, secrets en prompt-/chatinhoud worden nooit gelogd.
"""

from __future__ import annotations

import contextvars
import datetime as _dt
import json
import logging
import logging.config
import os
import time
import uuid
from typing import Any

# --- OTel is optioneel: importeer guarded zodat de app zonder de `otel`-extra blijft draaien. ---
try:  # pragma: no cover - triviale import-guard
    from opentelemetry import metrics as _ot_metrics
    from opentelemetry import trace as _ot_trace

    _OTEL_API = True
except ImportError:  # pragma: no cover
    _OTEL_API = False

logger = logging.getLogger(__name__)

# Veldnamen die nooit in een logregel mogen verschijnen (mirror van GEHEIME_VELDEN in logger.ts).
GEHEIME_VELDEN = {
    "authorization",
    "token",
    "bearer",
    "secret",
    "chat_secret",
    "password",
    "api_key",
    "apikey",
    "chatinput",
}

# Python-niveau → MCP-niveau (debug|info|warn|error).
_NIVEAU = {
    logging.DEBUG: "debug",
    logging.INFO: "info",
    logging.WARNING: "warn",
    logging.ERROR: "error",
    logging.CRITICAL: "error",
}

# Standaard-LogRecord-attributen; alles daarbuiten is een door de aanroeper meegegeven `extra`-veld.
_STD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "taskName"}

# Per-request correlatie-id (gezet door RequestContextMiddleware); leeg buiten een request.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")

_geconfigureerd = False


def _trace_context() -> dict[str, str]:
    """Geef `{trace_id, span_id}` van de actieve span, of leeg als er geen (recording) span is."""
    if not _OTEL_API:
        return {}
    try:
        span = _ot_trace.get_current_span()
        ctx = span.get_span_context()
        if not ctx or not ctx.is_valid:
            return {}
        return {"trace_id": f"{ctx.trace_id:032x}", "span_id": f"{ctx.span_id:016x}"}
    except Exception:  # noqa: BLE001 - logging mag nooit omvallen
        return {}


class JsonFormatter(logging.Formatter):
    """Serialiseer elke LogRecord als één JSON-regel in de MCP-logvorm."""

    def format(self, record: logging.LogRecord) -> str:
        regel: dict[str, Any] = {
            "ts": _dt.datetime.fromtimestamp(record.created, _dt.timezone.utc).isoformat(),
            "niveau": _NIVEAU.get(record.levelno, "info"),
            "categorie": getattr(record, "categorie", "functioneel"),
            "logger": record.name,
            "bericht": record.getMessage(),
        }
        regel.update(_trace_context())
        rid = request_id_var.get()
        if rid:
            regel["request_id"] = rid
        # Vrije velden uit `extra=` meenemen (geredacteerd), behalve de interne stuurvelden.
        for k, v in record.__dict__.items():
            if k in _STD_ATTRS or k == "categorie":
                continue
            if k.lower() in GEHEIME_VELDEN or v is None:
                continue
            regel[k] = v
        if record.exc_info:
            regel["exception"] = self.formatException(record.exc_info)
        return json.dumps(regel, ensure_ascii=False, default=str)


def _dict_config(settings: Any) -> dict[str, Any]:
    is_json = getattr(settings, "log_format", "json").lower() != "text"
    level = getattr(settings, "log_level", "info").upper()
    formatter = (
        {"()": f"{__name__}.JsonFormatter"}
        if is_json
        else {"format": "%(asctime)s %(levelname)-7s %(name)s | %(message)s"}
    )
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"wa": formatter},
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "wa",
            }
        },
        "root": {"level": level, "handlers": ["stdout"]},
        # Vang uvicorn in hetzelfde format: laat hun records naar de root propageren, geen eigen handler.
        "loggers": {
            name: {"level": level, "handlers": [], "propagate": True}
            for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
        },
    }


def _setup_otel(settings: Any) -> None:
    """Zet OTLP-providers op voor traces/metrics/logs. No-op zonder endpoint of zonder de otel-extra."""
    endpoint = getattr(settings, "otel_endpoint", "") or ""
    if not endpoint:
        return
    if not _OTEL_API:
        logger.warning(
            "OTEL_EXPORTER_OTLP_ENDPOINT is gezet maar opentelemetry ontbreekt; "
            "installeer de 'otel'-extra. OpenTelemetry blijft uit."
        )
        return
    try:
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": getattr(settings, "otel_service_name", "wetsanalyse-api")})
        _setup_traces(resource)
        if getattr(settings, "otel_metrics_enabled", True):
            _setup_metrics(resource)
        _setup_logs(resource)
        _instrument_libraries()
        logger.info("OpenTelemetry actief", extra={"categorie": "functioneel", "otel_endpoint": endpoint})
    except Exception:  # noqa: BLE001 - observability mag de start nooit blokkeren
        logger.warning("OpenTelemetry-setup mislukt (genegeerd)", exc_info=True)


def _proto() -> str:
    return os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf").lower()


def _setup_traces(resource: Any) -> None:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    if _proto().startswith("grpc"):
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    else:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    _ot_trace.set_tracer_provider(provider)


def _setup_metrics(resource: Any) -> None:
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

    if _proto().startswith("grpc"):
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    else:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    _ot_metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))


def _setup_logs(resource: Any) -> None:
    """Stuur stdlib-logs óók via OTLP (naast de JSON-stdout-regels) door een LoggingHandler op root."""
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

    if _proto().startswith("grpc"):
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    else:
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    set_logger_provider(provider)
    logging.getLogger().addHandler(LoggingHandler(level=logging.INFO, logger_provider=provider))


def _instrument_libraries() -> None:
    """Auto-instrumenteer uitgaande httpx (MCP + chat-agent → traceparent) en de DB. Elk guarded."""
    for naam, doe in (("httpx", _instr_httpx), ("sqlalchemy", _instr_sqlalchemy), ("asyncpg", _instr_asyncpg)):
        try:
            doe()
        except Exception:  # noqa: BLE001
            logger.debug("OTel-instrumentatie van %s overgeslagen", naam, exc_info=True)


def _instr_httpx() -> None:
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    HTTPXClientInstrumentor().instrument()


def _instr_sqlalchemy() -> None:
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    SQLAlchemyInstrumentor().instrument()


def _instr_asyncpg() -> None:
    from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor

    AsyncPGInstrumentor().instrument()


def setup(settings: Any) -> None:
    """Configureer logging + OpenTelemetry. Idempotent; veilig om vroeg in main.py aan te roepen."""
    global _geconfigureerd
    if _geconfigureerd:
        return
    logging.config.dictConfig(_dict_config(settings))
    _setup_otel(settings)
    _geconfigureerd = True


def instrument_fastapi(app: Any) -> None:
    """Instrumenteer de FastAPI-app (inkomende requests → spans). No-op zonder de otel-extra/endpoint."""
    if not _OTEL_API:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except Exception:  # noqa: BLE001
        logger.debug("FastAPI-instrumentatie overgeslagen", exc_info=True)


_access_logger = logging.getLogger("wetsanalyse.access")


class RequestContextMiddleware:
    """Pure-ASGI-middleware: request-id-correlatie + één access-logregel per request.

    Bewust pure ASGI (geen BaseHTTPMiddleware): dat zou de SSE-streams van de API bufferen/breken.
    Leest/genereert `X-Request-Id`, bindt 'm in een ContextVar zodat álle logs binnen de request 'm
    dragen, echoot 'm in de response, en logt bij de eerste response-chunk method/path/status/duur.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        rid = headers.get(b"x-request-id", b"").decode() or uuid.uuid4().hex
        token = request_id_var.set(rid)
        start = time.perf_counter()
        status_code = 0

        async def send_wrapper(message: dict) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                resp_headers = message.setdefault("headers", [])
                resp_headers.append((b"x-request-id", rid.encode()))
                duur_ms = round((time.perf_counter() - start) * 1000, 1)
                _access_logger.info(
                    "%s %s -> %s",
                    scope.get("method", "?"),
                    scope.get("path", "?"),
                    status_code,
                    extra={
                        "categorie": "functioneel",
                        "http_method": scope.get("method"),
                        "http_path": scope.get("path"),
                        "http_status": status_code,
                        "duur_ms": duur_ms,
                    },
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            request_id_var.reset(token)


# --- No-op-shims zodat de app onvoorwaardelijk tracers/meters mag gebruiken --------------------


class _NoopSpan:
    def set_attribute(self, *_a: Any, **_k: Any) -> None: ...
    def record_exception(self, *_a: Any, **_k: Any) -> None: ...
    def set_status(self, *_a: Any, **_k: Any) -> None: ...
    def add_event(self, *_a: Any, **_k: Any) -> None: ...
    def end(self, *_a: Any, **_k: Any) -> None: ...
    def __enter__(self) -> "_NoopSpan":
        return self
    def __exit__(self, *_a: Any) -> bool:
        return False


class _NoopInstrument:
    def add(self, *_a: Any, **_k: Any) -> None: ...
    def record(self, *_a: Any, **_k: Any) -> None: ...


class _NoopTracer:
    def start_as_current_span(self, *_a: Any, **_k: Any) -> _NoopSpan:
        return _NoopSpan()


class _NoopMeter:
    def create_counter(self, *_a: Any, **_k: Any) -> _NoopInstrument:
        return _NoopInstrument()
    def create_histogram(self, *_a: Any, **_k: Any) -> _NoopInstrument:
        return _NoopInstrument()
    def create_up_down_counter(self, *_a: Any, **_k: Any) -> _NoopInstrument:
        return _NoopInstrument()


def get_tracer(naam: str) -> Any:
    """Tracer voor de app. Reële tracer als OTel beschikbaar is (no-op provider als niet gezet), anders shim."""
    if _OTEL_API:
        return _ot_trace.get_tracer(naam)
    return _NoopTracer()


def get_meter(naam: str) -> Any:
    if _OTEL_API:
        return _ot_metrics.get_meter(naam)
    return _NoopMeter()
