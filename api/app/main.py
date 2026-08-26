"""FastAPI-app: routers, OpenAPI (Swagger op /docs → importeerbaar in Postman) en health/ready.
Sinds het verwijderen van de analyse-pijplijn bedient de app het annotatie-domein van de werkplek,
het LLM-/gebruikersbeheer en de wet-/profiel-keuzelijsten."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .shared import db, observability
from .shared.config import get_settings
from .features.annotatie import router as annotatie
from .features.api_tokens import router as api_tokens
from .features.berichten import router as berichten
from .features.feedback import router as feedback
from .features.gesprekken import router as gesprekken
from .features.identiteit_toegang import router as identiteit_toegang
from .features.llm_profielen import router as llm_profielen

# Configureer logging + OpenTelemetry vóór iets anders logt (idempotent; OTel is no-op zonder endpoint).
observability.setup(get_settings())

logger = logging.getLogger(__name__)


async def _wacht_op_db(engine) -> None:
    """Wacht tot de DB bereikbaar is, met **bounded retry** — géén schemabeheer hier (werkwijze-
    ADR-0005): het schema komt uitsluitend van `alembic upgrade head`, vóór het opstarten van de
    server (zie Dockerfile/README). Postgres draait als aparte stack (geen cross-stack
    `depends_on`), dus bij een cold start kan de DB nog niet klaar zijn wanneer de API opstart —
    dan retrye we i.p.v. crash-loopen. Knoppen: `WETSANALYSE_DB_CONNECT_RETRIES` (default 30) en
    `WETSANALYSE_DB_CONNECT_BACKOFF` (seconden, default 2) → ~60s venster."""
    import sqlalchemy.exc
    from sqlalchemy import text

    pogingen = int(os.environ.get("WETSANALYSE_DB_CONNECT_RETRIES", "30"))
    backoff = float(os.environ.get("WETSANALYSE_DB_CONNECT_BACKOFF", "2"))
    transient = (OSError, sqlalchemy.exc.OperationalError, sqlalchemy.exc.InterfaceError)
    for poging in range(1, pogingen + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # Globale LLM-concurrency-rem instellen (kostenbeheersing tegen zelf-veroorzaakte rate-limits;
    # de admin-verbindingstest is nu de enige LLM-call, maar de rem blijft goedkoop en veilig).
    from .features.llm_profielen.llm import throttle
    throttle.configure(settings.llm_max_concurrency)
    # Async SQLAlchemy-engine. Het schema zelf is Alembic's verantwoordelijkheid (`alembic upgrade
    # head`, vóór het starten van de server — zie Dockerfile/README), niet iets dat de app bij het
    # opstarten zelf aanmaakt (werkwijze-ADR-0005). Hier alleen wachten tot de DB bereikbaar is.
    db.init_engine(settings.database_url)
    await _wacht_op_db(db.get_engine())
    try:
        from .features.llm_profielen import store as profiles

        await profiles.ensure_seeded(settings)
    except Exception:  # noqa: BLE001 — seeding mag de start nooit blokkeren
        logger.exception("Seeden van het default-modelprofiel is mislukt")
    yield
    await db.dispose_engine()


app = FastAPI(
    title="Wetsanalyse API",
    version=__version__,
    description="Backend voor de Wetsanalyse-werkplek: het JAS-annotatiedomein, LLM-/gebruikersbeheer "
    "en wet-/profiel-keuzelijsten. Auth via per-client bearer-token.",
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

# De analyse-pijplijn (/v1/projects) is verwijderd; de API bedient nu het annotatie-domein van de
# werkplek, het LLM-/gebruikersbeheer en de wet-/profiel-keuzelijsten. Elke feature levert zijn eigen
# publieke router en, waar van toepassing, een aparte `admin_router` (achter require_admin).
app.include_router(llm_profielen.router, prefix="/v1")
app.include_router(llm_profielen.admin_router, prefix="/v1")
app.include_router(identiteit_toegang.router, prefix="/v1")
app.include_router(identiteit_toegang.admin_router, prefix="/v1")
app.include_router(api_tokens.router, prefix="/v1")
app.include_router(annotatie.router, prefix="/v1")
app.include_router(berichten.router, prefix="/v1")
app.include_router(berichten.admin_router, prefix="/v1")
app.include_router(feedback.router, prefix="/v1")
app.include_router(feedback.admin_router, prefix="/v1")
app.include_router(gesprekken.router, prefix="/v1")


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
        "llm_model_gezet": bool(s.llm_model),
        "database_geconfigureerd": bool(s.database_url),
    }
