"""Configuratie en projectpaden.

Bewust env-gebaseerd en zonder extra dependency (geen pydantic-settings). Alle paden zijn
afgeleid van de projectroot zodat de service portabel blijft, net als de rest van het project.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

# api/app/config.py -> api/app -> api -> <projectroot>
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# De canonieke JAS-klassenlijst leeft in het skill-script `validate_analyse.py`; `validation.py`
# laadt dat script op runtime in, zodat er één bron van waarheid is (zie api/Dockerfile).
SKILL_DIR = PROJECT_ROOT / ".claude" / "skills" / "wetsanalyse"
SKILL_SCRIPTS = SKILL_DIR / "scripts"


def _read_secret(env_name: str) -> str | None:
    """Lees een secret uit `${NAME}` of, als `${NAME}_FILE` is gezet, uit dat bestand.

    Het *_FILE-patroon spiegelt de MCP (Docker secret/vault) — secrets niet als plain env.
    """
    file_var = os.environ.get(f"{env_name}_FILE")
    if file_var:
        try:
            return Path(file_var).read_text(encoding="utf-8").strip()
        except OSError:
            return None
    val = os.environ.get(env_name)
    return val.strip() if val else None


class Settings:
    """Runtime-instellingen, één keer ingelezen uit de omgeving."""

    def __init__(self) -> None:
        # --- Auth: per-client tokens "id:token,id2:token2" (erf het MCP-patroon) ---
        raw_tokens = _read_secret("WETSANALYSE_API_TOKENS") or ""
        self.client_tokens: dict[str, str] = {}
        for part in raw_tokens.split(","):
            part = part.strip()
            if not part or ":" not in part:
                continue
            client_id, token = part.split(":", 1)
            self.client_tokens[token.strip()] = client_id.strip()
        # Fail-closed: leeg betekent "auth verplicht maar geen tokens" → alles 401.
        self.auth_required = os.environ.get("WETSANALYSE_AUTH_REQUIRED", "1") != "0"

        # --- Admin-auth: aparte tokens voor /v1/admin/* (LLM-beheer) ---
        raw_admin = _read_secret("WETSANALYSE_ADMIN_TOKENS") or ""
        self.admin_tokens: dict[str, str] = {}
        for part in raw_admin.split(","):
            part = part.strip()
            if not part or ":" not in part:
                continue
            admin_id, token = part.split(":", 1)
            self.admin_tokens[token.strip()] = admin_id.strip()

        # --- LLM-adapter ---
        # Endpointtype bepaalt provider-prefix/auth (zie Fase 0): azure_ai (Foundry/MaaS) vs azure (OpenAI).
        self.llm_provider = os.environ.get("LLM_PROVIDER", "azure_ai")
        self.llm_model = os.environ.get("LLM_MODEL", "")
        self.llm_api_base = os.environ.get("LLM_API_BASE", "")
        self.llm_api_key = _read_secret("LLM_API_KEY")
        self.llm_api_version = os.environ.get("LLM_API_VERSION")  # alleen Azure-OpenAI
        self.llm_output_strategy = os.environ.get("LLM_OUTPUT_STRATEGY", "prompt_and_parse")
        self.llm_temperature = float(os.environ.get("LLM_TEMPERATURE", "0"))
        # Harde wandklok-timeout per LLM-call (0 = uit). Voorkomt dat een hangende provider-
        # verbinding een worker langer vasthoudt dan bedoeld; spiegelt `mcp_timeout_s`. Een hele
        # act-2/act-3-ronde kan bij een traag provider-model >2 min duren — 300s i.p.v. 120s
        # voorkomt vals-terminale timeouts. Veilig t.o.v. de lease: de heartbeat ververst die
        # mid-call (zie orchestrator._heartbeat / WETSANALYSE_LEASE_S).
        self.llm_timeout_s = float(os.environ.get("WETSANALYSE_LLM_TIMEOUT_S", "300"))
        # Harde cap op het aantal prompt-tokens per LLM-call (0 = auto-afleiden uit het model;
        # onbekend model → geen limiet). Bij overschrijding faalt de call snel en duidelijk i.p.v.
        # een rauwe provider-400. Aanbevolen: ~5–10% onder het context window van het profiel-model.
        self.llm_max_prompt_tokens = int(os.environ.get("WETSANALYSE_LLM_MAX_PROMPT_TOKENS", "0"))
        # Prompt caching: markeer het stabiele system-blok (de references) als cachebaar zodat
        # opeenvolgende bronnen/rondes binnen één fase de references uit de cache lezen i.p.v.
        # ze elke call vol te betalen. Default aan; zet op 0 als de provider cache_control niet
        # ondersteunt (dan valt alles terug op het oude gedrag, zonder regressie).
        self.llm_prompt_caching = os.environ.get("WETSANALYSE_LLM_PROMPT_CACHING", "1") != "0"

        # Master key voor versleuteling-at-rest van via de admin-UI opgeslagen API-keys.
        # Geldige Fernet-key (32 url-safe base64-bytes); ontbreekt 'ie → geen key-opslag (fail-closed).
        self.llm_config_secret = _read_secret("LLM_CONFIG_SECRET")

        # Benoemde profielen → geen vrije model-string vanuit de client (governance).
        # De profielen leven in de database (beheerbaar via /v1/admin/profiles); de env-waarden
        # hierboven seeden bij de eerste start één default-profiel (zie app/profiles.py) en
        # blijven de fallback wanneer een profiel geen eigen API-key heeft.
        self.default_model_profile = os.environ.get("LLM_DEFAULT_PROFILE", "azure-sonnet")

        # --- Database (PostgreSQL via SQLAlchemy async; asyncpg-driver) ---
        # Connection string via secret (DATABASE_URL_FILE) zodat ingebedde credentials niet als
        # plain env in de container staan; valt terug op DATABASE_URL voor lokaal. In productie
        # levert de CloudNativePG-operator deze secret aan. Vorm: postgresql+asyncpg://user:pw@host:5432/db
        self.database_url = (
            _read_secret("DATABASE_URL") or "postgresql+asyncpg://localhost:5432/wetsanalyse"
        )

        # --- CORS ---
        # Default leeg = geen cross-origin browser-toegang (veilig). De BFF/clients praten
        # server→server met een bearer-token en worden niet door CORS geraakt; zet
        # CORS_ORIGINS alleen als een browser-origin rechtstreeks de API moet aanspreken.
        raw_origins = os.environ.get("CORS_ORIGINS", "")
        self.cors_origins: list[str] = [o.strip() for o in raw_origins.split(",") if o.strip()]

        # --- Build-herkomst (door CI meegegeven; zichtbaar op /health) ---
        self.git_sha = os.environ.get("GIT_SHA", "")
        self.build_time = os.environ.get("BUILD_TIME", "")

        # --- LLM-concurrency (kostenrem tegen zelf-veroorzaakte rate-limits) ---
        # Globaal plafond op het aantal GELIJKTIJDIGE LLM-calls (per proces). 0 = uit. De enige
        # LLM-call is nu de admin-verbindingstest, maar de rem blijft goedkoop en veilig.
        self.llm_max_concurrency = int(os.environ.get("WETSANALYSE_LLM_MAX_CONCURRENCY", "4"))

        # --- Misbruik-/kostenbeheersing (0 = uit) ---
        # Per-client request-rate op de muterende endpoints.
        self.rate_limit_max = int(os.environ.get("WETSANALYSE_RATE_LIMIT_MAX", "30"))
        self.rate_limit_window_s = float(os.environ.get("WETSANALYSE_RATE_LIMIT_WINDOW", "60"))
        # Aparte, krappe rate-limit op de admin-verbindingstest: die doet een echte (betaalde)
        # LLM-call en zit alleen achter het admin-token — een gelekt token mag geen kosten stapelen.
        self.admin_test_rate_max = int(os.environ.get("WETSANALYSE_ADMIN_TEST_RATE_MAX", "10"))
        self.admin_test_rate_window_s = float(os.environ.get("WETSANALYSE_ADMIN_TEST_RATE_WINDOW", "60"))

        # --- Observability (gestructureerde logging + OpenTelemetry) ---
        # Niet-geheim → gewone env (geen *_FILE). `log_format=text` is prettiger lokaal; json is default.
        # OTel is volledig no-op zolang otel_endpoint leeg is (zie app/observability.py).
        self.log_level = os.environ.get("LOG_LEVEL", "info")
        self.log_format = os.environ.get("LOG_FORMAT", "json")  # json | text
        self.otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
        self.otel_service_name = os.environ.get("OTEL_SERVICE_NAME", "wetsanalyse-api")
        self.otel_metrics_enabled = os.environ.get("OTEL_METRICS_ENABLED", "1") != "0"

@lru_cache
def get_settings() -> Settings:
    return Settings()
