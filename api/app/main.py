"""FastAPI-app: routers, OpenAPI (Swagger op /docs → importeerbaar in Postman), health/ready,
en startup-reconciliatie van onderbroken jobs."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__, db, observability
from .config import get_settings
from .deps import drain_tasks, get_engine
from .routers import admin, annotatie, auth, catalog, projects

# Configureer logging + OpenTelemetry vóór iets anders logt (idempotent; OTel is no-op zonder endpoint).
observability.setup(get_settings())

logger = logging.getLogger(__name__)


async def _init_db_met_retry() -> None:
    """Verbind met de DB en zet/lijn het schema uit, met **bounded retry**. Postgres draait als
    aparte stack (geen cross-stack `depends_on`), dus bij een cold start kan de DB nog niet klaar zijn
    wanneer de API opstart — dan retrye we i.p.v. crash-loopen. Knoppen: `WETSANALYSE_DB_CONNECT_RETRIES`
    (default 30) en `WETSANALYSE_DB_CONNECT_BACKOFF` (seconden, default 2) → ~60s venster."""
    import sqlalchemy.exc

    pogingen = int(os.environ.get("WETSANALYSE_DB_CONNECT_RETRIES", "30"))
    backoff = float(os.environ.get("WETSANALYSE_DB_CONNECT_BACKOFF", "2"))
    transient = (OSError, sqlalchemy.exc.OperationalError, sqlalchemy.exc.InterfaceError)
    for poging in range(1, pogingen + 1):
        try:
            await db.create_all()
            await db.reconcile_schema()
            if poging > 1:
                logger.info("DB-verbinding gelukt na %d pogingen", poging)
            return
        except transient as exc:  # noqa: PERF203
            if poging >= pogingen:
                logger.error("DB niet bereikbaar na %d pogingen — opgeven", pogingen)
                raise
            logger.warning(
                "DB nog niet bereikbaar (poging %d/%d: %s) — %.1fs backoff",
                poging, pogingen, type(exc).__name__, backoff,
            )
            await asyncio.sleep(backoff)


async def _reaper_loop(interval_s: int) -> None:
    """Periodieke reaper: ruimt runt-jobs met een verlopen lease op (worker weg/gecrasht).
    Mag de app nooit killen — fouten worden gelogd, niet doorgegooid."""
    while True:
        await asyncio.sleep(interval_s)
        try:
            await get_engine().reap_once()
        except Exception:  # noqa: BLE001
            logger.exception("Reaper-ronde is mislukt")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # Globale LLM-concurrency-rem instellen (kostenbeheersing tegen zelf-veroorzaakte rate-limits).
    from .llm import throttle
    throttle.configure(settings.llm_max_concurrency)
    # Async SQLAlchemy-engine + tabellen. In productie zou een migratietool (Alembic) het schema
    # beheren; voor de beproevingsfase volstaat create_all (idempotent: alleen ontbrekende tabellen).
    db.init_engine(settings.database_url)
    # create_all + reconcile_schema (idempotent) met bounded retry — vangt een nog-niet-klare DB bij
    # cold start op (postgres is een aparte stack zonder cross-stack depends_on).
    await _init_db_met_retry()
    try:
        from . import profiles

        await profiles.ensure_seeded(settings)
    except Exception:  # noqa: BLE001 — seeding mag de start nooit blokkeren
        logger.exception("Seeden van het default-modelprofiel is mislukt")
    try:
        await get_engine().reconcile_startup()
    except Exception:  # noqa: BLE001 — engine mag de start nooit blokkeren
        logger.exception("Startup-reconciliatie van onderbroken jobs is mislukt")
    reaper_task: asyncio.Task | None = None
    if settings.reaper_interval_s > 0:
        reaper_task = asyncio.create_task(_reaper_loop(settings.reaper_interval_s))
    yield
    if reaper_task is not None:
        reaper_task.cancel()
        try:
            await reaper_task
        except asyncio.CancelledError:
            pass
    # Lopende achtergrond-analyses netjes afronden/annuleren vóór de engine sluit.
    await drain_tasks()
    await db.dispose_engine()


app = FastAPI(
    title="Wetsanalyse API",
    version=__version__,
    description="Headless orchestratie van de Wetsanalyse (JAS). Async checkpoints; "
    "rapport.json als primaire bron. Auth via per-client bearer-token.",
    lifespan=lifespan,
)

settings = get_settings()
# Request-id-correlatie + access-logging (pure ASGI, veilig voor de SSE-streams).
app.add_middleware(observability.RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Inkomende requests → spans (no-op zonder de otel-extra/endpoint).
observability.instrument_fastapi(app)

# Eén kanonieke resource onder een versie-prefix (/v1/projects). De eerdere losse
# /analyses-router is geconsolideerd; clients migreren naar /v1/projects.
app.include_router(projects.router, prefix="/v1")
app.include_router(catalog.router, prefix="/v1")
app.include_router(admin.router, prefix="/v1")
app.include_router(auth.router, prefix="/v1")
app.include_router(annotatie.router, prefix="/v1")


@app.get("/health", tags=["meta"])
async def health():
    """Liveness — geen auth, mag niet falen op trage MCP/LLM."""
    s = get_settings()
    return {"status": "ok", "version": __version__, "git_sha": s.git_sha, "build_time": s.build_time}


@app.get("/ready", tags=["meta"])
async def ready():
    """Readiness — configuratie aanwezig? (geen netwerk-call om health niet te koppelen)."""
    s = get_settings()
    # Alleen booleans — geen interne URL's/hostnamen lekken aan een ongeauthenticeerd endpoint.
    return {
        "auth_geconfigureerd": bool(s.client_tokens) or not s.auth_required,
        "mcp_geconfigureerd": bool(s.mcp_url),
        "llm_model_gezet": bool(s.llm_model),
        "database_geconfigureerd": bool(s.database_url),
    }
