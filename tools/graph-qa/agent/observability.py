"""
Observability voor graph-qa: gestructureerde JSON-logging + OpenTelemetry.

Gespiegeld aan `api/app/observability.py` (zelfde logvorm en gate-gedrag) zodat de
frontend→API→graph-qa→MCP-keten in één trace valt en Loki/Alloy één logschema zien.

Twee lagen, allebei fail-open:
1. JSON-logging naar stdout (velden ts/niveau/categorie/logger/bericht + trace-context).
2. OpenTelemetry, alleen actief als `OTEL_EXPORTER_OTLP_ENDPOINT` gezet is én de
   `otel`-extra geïnstalleerd. Anders volledig no-op (nul overhead).

Nooit tokens/secrets/prompt- of chatinhoud loggen (AVG-dataminimalisatie).
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

try:  # OTel is optioneel — import guarded zodat graph-qa zonder de otel-extra draait.
    from opentelemetry import metrics as _ot_metrics
    from opentelemetry import trace as _ot_trace

    _OTEL_API = True
except ImportError:  # pragma: no cover
    _OTEL_API = False

logger = logging.getLogger(__name__)

GEHEIME_VELDEN = {"authorization", "token", "bearer", "secret", "password", "api_key", "apikey", "question"}

# Een stacktrace is diagnostisch goud, maar de exceptie-tékst erin draagt soms inhoud: een MCPError
# neemt een stukje responsbody mee, een providerfout een fragment van het verzoek. De belofte
# hierboven is absoluut ("nooit prompt- of chatinhoud"), dus knippen we per regel en op het geheel.
# Frames blijven daarmee intact — je ziet nog steeds wáár het misging — maar een lange payloadregel
# wordt afgekapt in plaats van integraal naar Loki te reizen.
_MAX_TRACE_REGEL = 300
_MAX_TRACE_REGELS = 40

_NIVEAU = {
    logging.DEBUG: "debug",
    logging.INFO: "info",
    logging.WARNING: "warn",
    logging.ERROR: "error",
    logging.CRITICAL: "error",
}

_STD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "taskName"}

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")

_geconfigureerd = False


def _trace_context() -> dict[str, str]:
    if not _OTEL_API:
        return {}
    try:
        ctx = _ot_trace.get_current_span().get_span_context()
        if not ctx or not ctx.is_valid:
            return {}
        return {"trace_id": f"{ctx.trace_id:032x}", "span_id": f"{ctx.span_id:016x}"}
    except Exception:  # noqa: BLE001
        return {}


def _kort_trace(trace: str) -> str:
    """Kap een stacktrace in op regel- en totaalniveau, met behoud van de frames.

    Bewust géén slimme redactie: die zou moeten raden wat inhoud is en wat niet. Afkappen is
    voorspelbaar — het type, het bestand en het regelnummer passen altijd, de payload niet.
    """
    regels = [r if len(r) <= _MAX_TRACE_REGEL else r[:_MAX_TRACE_REGEL] + " …[ingekort]"
              for r in (trace or "").splitlines()]
    if len(regels) > _MAX_TRACE_REGELS:
        # Begin en eind zijn het informatiefst: waar het vandaan komt en waar het knalde.
        helft = _MAX_TRACE_REGELS // 2
        weg = len(regels) - 2 * helft
        regels = regels[:helft] + [f"  …[{weg} frames ingekort]"] + regels[-helft:]
    return "\n".join(regels)


class JsonFormatter(logging.Formatter):
    """Serialiseer elke LogRecord als één JSON-regel in de gedeelde logvorm."""

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
        for k, v in record.__dict__.items():
            if k in _STD_ATTRS or k == "categorie":
                continue
            if k.lower() in GEHEIME_VELDEN or v is None:
                continue
            regel[k] = v
        if record.exc_info:
            regel["exception"] = _kort_trace(self.formatException(record.exc_info))
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
        "formatters": {"qa": formatter},
        "handlers": {
            "stdout": {"class": "logging.StreamHandler", "stream": "ext://sys.stdout", "formatter": "qa"}
        },
        "root": {"level": level, "handlers": ["stdout"]},
        "loggers": {
            name: {"level": level, "handlers": [], "propagate": True}
            for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
        },
    }


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


def _instr_httpx() -> None:
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    HTTPXClientInstrumentor().instrument()


def _setup_otel(settings: Any) -> None:
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

        resource = Resource.create({"service.name": getattr(settings, "otel_service_name", "graph-qa")})
        _setup_traces(resource)
        if getattr(settings, "otel_metrics_enabled", True):
            _setup_metrics(resource)
        try:
            _instr_httpx()  # uitgaande MCP-calls dragen traceparent → keten sluit
        except Exception:  # noqa: BLE001
            logger.debug("httpx-instrumentatie overgeslagen", exc_info=True)
        logger.info("OpenTelemetry actief", extra={"otel_endpoint": endpoint})
    except Exception:  # noqa: BLE001 - observability mag de start nooit blokkeren
        logger.warning("OpenTelemetry-setup mislukt (genegeerd)", exc_info=True)


def setup(settings: Any) -> None:
    """Configureer logging + OpenTelemetry. Idempotent; vroeg in main.py aanroepen."""
    global _geconfigureerd
    if _geconfigureerd:
        return
    logging.config.dictConfig(_dict_config(settings))
    _setup_otel(settings)
    _geconfigureerd = True


def shutdown() -> None:
    """Flush + sluit de OTel-providers netjes af zodat de laatste gebufferde spans/metrics bij een
    container-stop niet verloren gaan. No-op als OTel niet actief is. Aanroepen in de app-shutdown."""
    if not _OTEL_API:
        return
    for _get in (
        getattr(_ot_trace, "get_tracer_provider", None),
        getattr(_ot_metrics, "get_meter_provider", None),
    ):
        try:
            provider = _get() if _get else None
            if provider is not None and hasattr(provider, "shutdown"):
                provider.shutdown()  # flush'et de BatchSpanProcessor/MetricReader
        except Exception:  # noqa: BLE001 — shutdown mag de app-stop nooit breken
            logger.debug("OTel-provider shutdown overgeslagen", exc_info=True)


def instrument_fastapi(app: Any) -> None:
    if not _OTEL_API:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except Exception:  # noqa: BLE001
        logger.debug("FastAPI-instrumentatie overgeslagen", exc_info=True)


_access_logger = logging.getLogger("graph_qa.access")


class RequestContextMiddleware:
    """Pure-ASGI: X-Request-Id-correlatie + één access-logregel per request.

    Bewust pure ASGI (geen BaseHTTPMiddleware), zodat de SSE-stream niet gebufferd wordt.
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

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"x-request-id", rid.encode()))
                _access_logger.info(
                    "%s %s -> %s",
                    scope.get("method", "?"),
                    scope.get("path", "?"),
                    message["status"],
                    extra={
                        "http_method": scope.get("method"),
                        "http_path": scope.get("path"),
                        "http_status": message["status"],
                        "duur_ms": round((time.perf_counter() - start) * 1000, 1),
                    },
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            request_id_var.reset(token)


# --- No-op-shims zodat code onvoorwaardelijk spans/metrics mag maken ---------------------------

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


class _NoopTracer:
    def start_as_current_span(self, *_a: Any, **_k: Any) -> _NoopSpan:
        return _NoopSpan()


def get_tracer(naam: str) -> Any:
    if _OTEL_API:
        return _ot_trace.get_tracer(naam)
    return _NoopTracer()
