FROM python:3.14-slim

WORKDIR /app

# Pip eerst upgraden zodat de base-image-pip (met bekende CVE's) niet in de image achterblijft —
# Trivy scant 'm anders als alert — en zijn vendored bom.cdx.json meteen weg: pip 26.x bakt een
# CycloneDX-SBOM van zijn eigen vendored deps mee die Trivy als package-inventaris leest en los van
# de echt geïnstalleerde versies als kwetsbaar rapporteert. Zelfde fix als in api/Dockerfile.
RUN pip install --no-cache-dir --upgrade pip 'setuptools>=83.0.0' \
 && rm -f /usr/local/lib/python3.14/site-packages/pip/_vendor/bom.cdx.json

COPY pyproject.toml ./
COPY agent/ agent/
COPY api/ api/

# Installeren uit pyproject.toml, mét de 'otel'-extra (zodat OTel werkt zodra
# OTEL_EXPORTER_OTLP_ENDPOINT gezet is; zonder die packages degradeert observability naar alleen
# JSON-logs zónder trace_id).
#
# Bewust géén handmatig herhaalde pip-lijst hier: die liep uit de pas met pyproject.toml, waardoor
# langgraph-checkpoint-postgres en psycopg ontbraken en de agent bij een gezette CHECKPOINT_DB_URL
# omviel met "No module named 'langgraph.checkpoint.postgres'". Eén lijst, één bron van waarheid.
RUN pip install --no-cache-dir '.[otel]' "msgpack>=1.1.0"

# Non-root + /data voor de durable checkpointer-db (named volume; CHECKPOINT_DB_PATH=/data/...).
#
# `chmod -R a+rX /app` maakt de build onafhankelijk van de umask van wie 'm bouwt: COPY neemt de
# bronpermissies over, dus met een strakke umask (077) belandt de code als 0600/root in de image en
# kan appuser 'm niet lezen — de container faalt dan op "PermissionError: /app/api/__init__.py".
# In CI (umask 022) valt dat niet op, lokaal wel. a+rX zet leesrechten en houdt +x alleen op mappen.
RUN useradd -u 10001 -m appuser && mkdir -p /data && chown appuser:appuser /data \
    && chmod -R a+rX /app
USER appuser

EXPOSE 8080

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
