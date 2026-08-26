# Build-context = projectroot (de API leest de skill-references/scripts via PROJECT_ROOT).
# Bouwen vanaf de root:  docker build -f api/Dockerfile -t wetsanalyse-api .
# CI (api-docker-publish.yml) pusht de image naar GHCR; Portainer pullt :latest.

# ── Builder ───────────────────────────────────────────────────────────────────
# uv leeft alléén in deze stage: het bouwt de .venv en blijft daarna buiten de
# runtime-image (anders scant Trivy de uv-binary en z'n gebundelde crates mee).
FROM python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6 AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11@sha256:ff07b86af50d4d9391d9daf4ff89ce427bc544f9aae87057e69a1cc0aa369946 /uv /bin/uv

# Forceer de systeem-Python van de base-image: dan symlinkt de .venv naar
# /usr/local/bin/python3.14 — een pad dat óók in de identieke runtime-stage bestaat.
# Zonder dit zou uv een eigen "managed" Python kunnen downloaden en breekt de COPY.
ENV UV_PYTHON_PREFERENCE=only-system

WORKDIR /app/api

# Eerst alleen de dependency-manifesten → betere layer-cache. --extra llm: de engine
# (LiteLLM + MCP-client) is in productie nodig. --extra otel: OpenTelemetry, zodat een gezette
# OTEL_EXPORTER_OTLP_ENDPOINT werkt (gated op runtime; zonder endpoint gebeurt er niets).
# De lock zorgt voor reproduceerbare builds.
COPY api/pyproject.toml api/uv.lock /app/api/
RUN uv sync --extra llm --extra otel --frozen

# uv laat een gebundelde setuptools 70.3.0 in de .venv achter; Trivy scant die venv
# (de runtime-pip-bump raakt alleen /usr/local/lib, niet /app/api/.venv). Overschrijf
# 'm binnen de venv — dekt CVE-2025-47273 (HIGH, Path Traversal) én CVE-2026-59890
# (MEDIUM, MANIFEST.in bypass via Unicode-normalisatie).
RUN uv pip install --python /app/api/.venv/bin/python --no-cache-dir 'setuptools>=83.0.0'

# ── Runtime ───────────────────────────────────────────────────────────────────
# Schone base, identiek aan de builder → de venv-symlinks naar /usr/local/bin/python
# blijven geldig. Geen uv meer; systeem-pip naar een gepatchte versie (BIO2 / ISO 27002).
FROM python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6 AS runtime

# OS-pakketten patchen (BIO2 / ISO 27002:2022 §8.8), spiegelt de MCP-/frontend-image.
# De base-image loopt soms achter op Debian-security-updates (o.a. liblzma5, CVE-2026-34743).
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade 'pip>=26.1' 'setuptools>=83.0.0' \
 && rm -f /usr/local/lib/python3.14/site-packages/pip/_vendor/bom.cdx.json
# ↑ pip 26.x bakt een CycloneDX-SBOM van zijn vendored deps mee (msgpack 1.1.2,
# setuptools 70.3.0, …). Trivy pikt die op als "third-party SBOM" en rapporteert
# die versies als kwetsbaar — ook al is de echte image al gepatcht. Verwijderen
# sluit de valse alerts zonder pip-functionaliteit te breken.

WORKDIR /app/api

# De gebouwde virtualenv uit de builder (bevat alle runtime-dependencies).
COPY --from=builder /app/api/.venv /app/api/.venv

# Applicatiecode + de gedeelde wetsanalyse-skill-kennis (references/scripts). `validation.py` laadt
# op import-tijd `validate_analyse` uit die skill voor de canonieke JAS-klassenlijst, dus de skill
# moet mee in de image.
COPY api /app/api
COPY .claude/skills/wetsanalyse /app/.claude/skills/wetsanalyse

# Build-herkomst, door CI meegegeven → leesbaar voor de service op /health (deploy-pariteit).
ARG GIT_SHA=""
ARG BUILD_TIME=""
ENV PATH="/app/api/.venv/bin:$PATH" \
    GIT_SHA=$GIT_SHA \
    BUILD_TIME=$BUILD_TIME

EXPOSE 3000

# Non-root + read-only-fs-proof: de service schrijft niet naar de filesystem (opslag = PostgreSQL).
# We maken /app groep-root-eigendom met groep=gebruiker-rechten, zodat de container ook onder een
# willekeurige UID (lid van groep 0) de code kan lezen/uitvoeren. HOME=/tmp zodat eventuele
# home-caches naar een schrijfbare (tmpfs) plek gaan i.p.v. een niet-schrijfbare root-fs. USER 10001.
RUN useradd --no-create-home --uid 10001 --gid 0 appuser \
    && chgrp -R 0 /app && chmod -R g=u /app
ENV HOME=/tmp
USER 10001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:3000/health').status==200 else 1)"

# Conservatieve default van één worker. De request-afhandeling is stateless (de opslag is de
# gedeelde PostgreSQL), dus `--workers >1` en meerdere replica's zijn veilig — verhoog dit gerust
# voor horizontaal schalen.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000", "--workers", "1"]
