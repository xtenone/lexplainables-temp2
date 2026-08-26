# wetsanalyse-api

Headless HTTP-backend voor de **Wetsanalyse-werkplek** — een kerncomponent van het agent-platform,
onder de [frontend](../frontend). De API bedient het **JAS-annotatiedomein** van de werkplek
(documenten/elementen/beslissingen + append-only auditlog), het **login-/gebruikersbeheer** (de API is
de identiteitsbron), het **LLM-modelprofielbeheer**, de **profiel-keuzelijst**, de **berichten** (release notes) en de **gebruikersfeedback**.

> **De QA/annotatie-agent is een aparte dienst.** `tools/graph-qa/` beantwoordt de vragen, stelt
> de JAS-annotaties voor en levert de wettekst uit de graaf; de werkplek praat er direct mee (SSE).
> Deze API bewaart de review-state en bedient login en beheer.

## Hoe het past in het project

| Onderdeel | Rol |
|-----------|-----|
| **graph-qa** | **Lex**, de assistent voor wetsanalyse — beantwoordt vragen, stelt JAS-annotaties voor en levert de wettekst (uit de graaf); de werkplek praat er direct mee. Eigen LLM-config. |
| **wetsanalyse-api** *(deze map)* | HTTP-harness — annotatiedomein, login, LLM-/gebruikersbeheer, profiel-keuzelijst. |
| **PostgreSQL** | Opslag — annotatie-documenten + auditlog, modelprofielen, gebruikers, API-tokens. |

## Endpoints

Alle endpoints zijn client-gescopet en versioneerd onder `/v1`.

**Annotatiedomein (de werkplek):**

| Methode | Pad | Wat het doet |
|---------|-----|--------------|
| `POST` | `/v1/annotatie/documenten` | Annotatie-document aanmaken |
| `GET` `DELETE` | `/v1/annotatie/documenten/{slug}` | Document ophalen / verwijderen |
| `PUT` | `/v1/annotatie/documenten/{slug}/elementen` | Door de agent voorgestelde JAS-elementen opslaan |
| `POST` | `/v1/annotatie/documenten/{slug}/elementen/{id}/beslissing` | Human-decision (approve/edit/reject/comment) |
| `GET` | `/v1/annotatie/documenten/{slug}/audit` | Append-only auditlog van het document |

**Keuzelijsten (client-auth, geen geheimen):**

| Methode | Pad | Wat het doet |
|---------|-----|--------------|
| `GET` | `/v1/profiles` | Keuzelijst modelprofielen (alleen naam + default) |
| `GET` | `/health` | Liveness check |
| `GET` | `/ready` | Readiness check (booleans: auth, LLM, MCP, database geconfigureerd) |

**Admin-endpoints (LLM-/catalogus-/gebruikersbeheer) achter een apart admin-token, onder `/v1/admin`:**

| Methode | Pad | Wat het doet |
|---------|-----|--------------|
| `GET` | `/v1/admin/profiles` | Lijst modelprofielen (key nooit, alleen `api_key_set`) |
| `PUT` | `/v1/admin/profiles/{name}` | Maak/werk profiel bij (API-key write-only) |
| `DELETE` | `/v1/admin/profiles/{name}` | Verwijder (niet de default) |
| `POST` | `/v1/admin/profiles/{name}/default` | Markeer als default |
| `POST` | `/v1/admin/profiles/{name}/test` | Test de verbinding (kleine LLM-call) |
| `GET` | `/v1/admin/users` | Lijst login-accounts (userid, e-mail, rol, 2FA-aan, actief) |
| `POST` | `/v1/admin/users` | Maak een account (geeft eenmalig een tijdelijk wachtwoord) |
| `PATCH` | `/v1/admin/users/{userid}` | Wijzig rol/actief (laatste actieve beheerder beschermd) |
| `POST` | `/v1/admin/users/{userid}/reset-password` | Nieuw tijdelijk wachtwoord |
| `DELETE` | `/v1/admin/users/{userid}` | Verwijder account |
| `GET` | `/v1/admin/api-tokens` | Lijst genereerbare API-tokens (nooit de hash/het volledige token) |
| `POST` | `/v1/admin/api-tokens` | Maak een API-token (eenmalig teruggegeven) |
| `DELETE` | `/v1/admin/api-tokens/{id}` | Trek een API-token in |

**Login-endpoints (de webapp-BFF is de enige client; achter het client-token), onder `/v1/auth`:**

| Methode | Pad | Wat het doet |
|---------|-----|--------------|
| `GET` | `/v1/auth/setup-status` | Is de users-tabel nog leeg? (dan staat de eenmalige registratie open) |
| `POST` | `/v1/auth/setup` | Maak de allereerste beheerder (alleen bij lege tabel → anders 409) |
| `POST` | `/v1/auth/verify` | Valideer **userid** + wachtwoord (+ optionele TOTP) |
| `GET` | `/v1/auth/me` | Eigen account (rol + 2FA-status) — `X-User-Id`-header |
| `POST` | `/v1/auth/change-password` | Eigen wachtwoord wijzigen — `X-User-Id`-header |
| `POST` | `/v1/auth/2fa/{begin,activate,disable}` | Optionele TOTP-2FA, self-service — `X-User-Id`-header |

Swagger-UI beschikbaar op `/docs`.

## Model-profielen (welk LLM)

De LLM-configuratie leeft in **benoemde modelprofielen** in de database (provider, model, endpoint,
temperatuur, versleutelde API-key), niet in losse env-vars. Beheer ze via de admin-endpoints hierboven
of het `/beheer`-scherm in de [frontend](../frontend); de verbindingstest (`/test`) valideert een
profiel met een kleine LLM-call. De env-`LLM_*`-waarden seeden bij de eerste start één default-profiel
en blijven de fallback-key. (De QA/annotatie-agent `graph-qa` draait als aparte dienst met een eigen
LLM-config — deze profielen sturen die agent niet aan.)

## Snel starten (lokaal)

```powershell
# 1. Secrets aanmaken in api\secrets\ (gitignored)
mkdir api\secrets
[IO.File]::WriteAllText("$PWD\api\secrets\api_tokens",       "lokaal:<token>")
# Voor het LLM-beheer (/v1/admin/*) — optioneel lokaal:
[IO.File]::WriteAllText("$PWD\api\secrets\admin_tokens",      "admin:<admin-token>")
# Fernet-master-key (versleutelt API-keys uit de admin-UI); genereer met:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
[IO.File]::WriteAllText("$PWD\api\secrets\llm_config_secret", "<fernet-key>")

# 2. .env aanmaken (kopieer .env.example en vul in)

# 3. PostgreSQL draaien (de opslag)
docker run -d -p 5432:5432 --name wetsanalyse-postgres-lokaal \
  -e POSTGRES_USER=wetsanalyse -e POSTGRES_PASSWORD=wetsanalyse -e POSTGRES_DB=wetsanalyse postgres:16

# 4. Server starten (--env-file is verplicht)
cd api
uv sync --extra llm --extra dev
uv run --env-file .env uvicorn app.main:app --reload --port 3000
```

Zet `DATABASE_URL=postgresql+asyncpg://wetsanalyse:wetsanalyse@localhost:5432/wetsanalyse` in `.env`;
de tabellen worden bij de start aangemaakt. Zie `CLAUDE.md` voor de volledige opstapinstructies, Azure
AI Foundry-config en productie-deployment via Docker/Portainer.

## Authenticatie

Elke request vereist een bearer-token: `Authorization: Bearer <token>`.
Tokens worden geconfigureerd via `WETSANALYSE_API_TOKENS_FILE` in het formaat `id:token,...`.
Zet `WETSANALYSE_AUTH_REQUIRED=0` om auth lokaal uit te zetten.

De **admin-endpoints** (`/v1/admin/*`) gebruiken een aparte tokenlijst `WETSANALYSE_ADMIN_TOKENS(_FILE)`
(zelfde `id:token,...`-vorm) plus intrekbare, genereerbare DB-tokens (`/v1/admin/api-tokens`), en zijn
**altijd** auth-plichtig — geen `AUTH_REQUIRED`-bypass; zonder admin-tokens geeft alles 401. Het opslaan
van een API-key via de admin-UI vereist daarnaast een Fernet-master-key in `LLM_CONFIG_SECRET(_FILE)`.

## Observability

De API is **geïnstrumenteerd**: gestructureerde JSON-logging (request-id-middleware, secret-redactie)
plus OpenTelemetry (traces/metrics/logs), gated op **`OTEL_EXPORTER_OTLP_ENDPOINT`** — leeg = no-op,
alleen logs. Eén trace-id verbindt frontend → API → MCP/graph-qa. Nooit tokens/secrets/prompt-inhoud
loggen. Zie `app/observability.py` en de projectbrede
[`docs/observability.md`](../docs/observability.md) (env-vars, logschema, en de optionele
Grafana-stack in `deploy/observability/`).
