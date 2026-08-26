# graph-qa — deployment (Portainer, intern)

De graph-qa-agent draait als intern-only Portainer-stack. De **werkplek** (frontend `/workbench`) belt
hem rechtstreeks op `POST /v1/chat` (SSE) via een server-side BFF-route — server→server over het
gedeelde netwerk `wetsanalyse_internal`. **Geen host-poort, geen publieke NPM-host nodig.** Image van GHCR via
`.github/workflows/graph-qa-docker-publish.yml`.

## 1. Host-secrets (eenmalig, op de host)

Bestanden in `SECRETS_DIR` (default `/opt/secrets/graph-qa`), leesbaar voor de
non-root container-user (uid 10001) → **chmod 644**:

```bash
SECRETS_DIR=/opt/secrets/graph-qa
sudo mkdir -p "$SECRETS_DIR"
echo -n "<GRAPHDB_TOKEN>"        | sudo tee "$SECRETS_DIR/graphdb_token"        >/dev/null
echo -n "<AZURE_FOUNDRY_API_KEY>"| sudo tee "$SECRETS_DIR/azure_foundry_api_key">/dev/null
# De uitkomst van een beurt zelf vastleggen (chatbericht + annotatiedocument), zodat een antwoord
# niet meer afhangt van een browser die blijft kijken. Zet dit token óók als eigen client-id in de
# api-stack: WETSANALYSE_API_TOKENS krijgt er `,graph-qa:<zelfde token>` bij.
# LET OP: mét dit token weigert graph-qa te starten als `qa_api_token` ontbreekt — een open endpoint
# dat namens elke gebruiker kan schrijven is geen optie.
echo -n "<GRAPH_QA_API_TOKEN>"   | sudo tee "$SECRETS_DIR/wetsanalyse_api_token" >/dev/null
echo -n "<GRAPH_QA_TOKEN>"       | sudo tee "$SECRETS_DIR/qa_api_token"          >/dev/null
# Optioneel — gedeeld, horizontaal-veilig gespreksgeheugen op de bestaande Postgres-stack (zie §4).
# psycopg-scheme (`postgresql://`, NIET `+asyncpg`); zelfde credentials als de postgres-stack.
echo -n "postgresql://wetsanalyse:<POSTGRES_PASSWORD>@postgres:5432/wetsanalyse" \
        | sudo tee "$SECRETS_DIR/checkpoint_db_url" >/dev/null
sudo chmod 755 "$SECRETS_DIR"; sudo chmod 644 "$SECRETS_DIR"/*
```
De waarden staan in `tools/graph-qa/.env`. **Geen chat-secret nodig:** de service is intern-only. Laat
`checkpoint_db_url` weg om het geheugen op het lokale `/data`-volume te houden (zie §4).

## 2. Stack

`deploy/docker-compose.yml`. Niet-geheime stack-env (Portainer of CI):
`GRAPH_QA_IMAGE`, `SECRETS_DIR`, `AZURE_FOUNDRY_BASE_URL`, `LLM_MODEL`, `GRAPHDB_MCP_URL`,
`SIMILARITY_INDEX` (`bwb_similarity`), `OTEL_EXPORTER_OTLP_ENDPOINT` (optioneel). Secrets via
`*_FILE` → `/run/secrets`. Gespreksgeheugen: zie §4.

De stack joint op **drie externe netwerken**, die dus alle drie moeten bestaan:

| netwerk | env | van wie | waarvoor |
|---|---|---|---|
| `wetsanalyse_internal` | `WA_NETWORK` | `deploy/postgres/` | de frontend belt graph-qa; graph-qa belt postgres |
| `graphdb_default` | `GRAAF_NETWORK` | `deploy/graphdb/` | de MCP achter `mcp-auth-proxy:8004` |
| `observability_default` | `OBS_NETWORK` | `deploy/observability/` | OTLP naar de collector |

**Health:** de container heeft een healthcheck op `/health`; een deploy faalt als de container niet
`(healthy)` wordt. Van buiten is de agent bewust niet bereikbaar — controleer dus op de host:
`docker exec graph-qa python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8080/health').status)"`.

## 3. Werkplek koppelen

De werkplek zit in de **frontend-stack**, niet in graph-qa. Wijs de frontend naar deze service via env
(zie `frontend/`): `GRAPH_QA_URL` (default intern `http://graph-qa:8080`). De BFF-route
`app/api/annotatie/agent` streamt `POST /v1/chat` door en `app/api/annotatie/artikel` haalt `GET /v1/artikel`
op; `conversation_id` geeft geheugen-continuïteit per gesprek. Bij een intern-only deployment is er geen
slot nodig. Verifieer via de Lex-pagina (`/workbench`).

> Wil je graph-qa tóch achter een token zetten: zet `QA_API_TOKEN_FILE=/run/secrets/qa_api_token` in deze
> stack, leg `qa_api_token` op de host, en geef de frontend hetzelfde token mee via `GRAPH_QA_TOKEN(_FILE)`.

## 4. Gespreksgeheugen (checkpointer)

Het gespreksgeheugen (`conversation_id` = LangGraph-`thread_id`; volledige historie terug naar het model)
loopt via een checkpointer. Backend-keuze (voorrang), zie `agent/agent.py:_checkpointer_ctx`:

1. **`CHECKPOINT_DB_URL`** → **Postgres** (`AsyncPostgresSaver`). Gedeeld tussen replica's →
   **horizontaal veilig**. **Verplicht zodra graph-qa >1 replica draait.** In deze stack: leg het
   host-secret `checkpoint_db_url` (§1) — het compose-bestand wijst er al naar via
   `CHECKPOINT_DB_URL_FILE`. De graph-qa-stack moet op hetzelfde netwerk als de postgres-stack zitten
   (`wetsanalyse_internal`, default) zodat `postgres:5432` bereikbaar is. Zelfde DB als de API; de
   checkpoint-tabellen (`checkpoints`/`checkpoint_*`) botsen niet met de API-tabellen — `setup()` maakt
   ze idempotent aan bij de eerste start.
2. **Geen URL** → `CHECKPOINT_DB_PATH` op het durabele **`graph_qa_data`-volume** (`/data`, `AsyncSqliteSaver`).
   Durabel, maar **per-instance** — alleen goed bij **één** replica.

Een gesprek verwijderen in de werkplek wist ook het agent-geheugen: de BFF roept
`DELETE /v1/conversations/{id}` aan (naast de API-berichten-delete).

## Deployvolgorde

`postgres` → `graphdb` → `observability` → **graph-qa** → `frontend`. De eerste drie maken de
netwerken waar deze stack op joint; de frontend verwijst naar `graph-qa:8080`.

De publish-workflow bouwt alleen het image naar GHCR (met Trivy-gate); de stack-update doe je daarna
via Portainer of de Portainer-API.
