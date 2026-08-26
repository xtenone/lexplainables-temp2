# CLAUDE.md — wetsanalyse-api

Headless API-backend voor de **Wetsanalyse-werkplek** — een kerncomponent van het agent-platform, een
zelfstandige, Dockeriseerbare dienst die je via HTTP (Postman/Swagger) bevraagt en die de
[frontend](../frontend) (de werkplek + login + `/beheer`) bedient. Lees ook de projectroot-`CLAUDE.md`.

## Scope: wat deze API nog doet

De API bedient zeven dingen:

1. **Het JAS-annotatiedomein van de werkplek** (`/v1/annotatie/*`): documenten/elementen/beslissingen
   + append-only auditlog + **export** (pdf/csv/json). De agent stelt voor, de mens beslist; de API bewaart de review-state.
   **Per-gebruiker gescopet** via de vertrouwde `X-User-Id`-header (`actieve_userid`, net als de
   gesprekken; 404 op andermans document). De bearer-`client_id` blijft als herkomst in de audit.
2. **De chatgeschiedenis van de werkplek** (`/v1/gesprekken/*`): gesprekken + geordende berichten
   (`gesprek_contracts.py`/`gesprek_store.py`/`routers/gesprekken.py`). Net als het annotatie-domein
   **per-gebruiker gescopet** via de vertrouwde `X-User-Id`-header (`actieve_userid`, hergebruikt uit
   de auth-router; 404 op andermans gesprek). Een bericht kan naar een annotatie-document verwijzen
   (`annotatie_slug`); de review-state zelf blijft in het annotatie-domein. Die verwijzing heeft
   **geen foreign key**, dus draagt het bericht er zijn eigen leesbare label bij (`annotatie_titel`):
   wordt het document later verwijderd, dan blijft het gesprek leesbaar in plaats van naar een
   naamloze slug te wijzen. `DELETE` van een annotatie-document raakt de berichten bewust niet — het
   gesprek is een verslag van wat er gebeurde. Een bericht draagt daarnaast optioneel een `run_id`:
   dat is een **idempotentiesleutel**, want een agent-beurt hangt niet meer aan één browserverbinding
   en er kunnen meerdere tabbladen op dezelfde run meekijken. `voeg_bericht_toe` weigert een tweede
   bericht met hetzelfde `run_id` en geeft het bestaande terug (check-then-insert binnen de
   transactie; géén unieke index, want `reconcile_schema` voegt die op bestaande tabellen niet toe —
   bij een tweede API-replica is dat niet meer genoeg). De schrijver is meestal **graph-qa**, niet de
   webapp: die legt de uitkomst van een beurt zelf vast en heeft daarvoor een eigen client-id in
   `WETSANALYSE_API_TOKENS` (`graph-qa:<token>`) plus de `X-User-Id` van de jurist. Let op wat dat
   betekent: `client_id` is niet aan `user_id` gebonden, dus dat token kan in elk gebruikersgesprek
   schrijven — graph-qa blijft daarom intern-only.
3. **Login + gebruikersbeheer** (`/v1/auth/*` + `/v1/admin/users`): de API is de identiteitsbron van
   de webapp (userid + wachtwoord, rollen, optionele TOTP-2FA).
4. **LLM-modelprofielbeheer** (`/v1/admin/profiles`).
5. De **profiel-keuzelijst** voor de UI (`/v1/profiles`).
6. **Berichten** (`/v1/berichten/*` + `/v1/admin/berichten/*`): release notes die beheerders
   publiceren en analisten lezen, met leesbewijzen per (bericht, user).
7. **Gebruikersfeedback** (`/v1/feedback` + `/v1/admin/feedback/*`): onwijzigbare meldingen uit de
   webapp. Elke beheerder heeft een eigen `feedback_gezien_op`, dus de ongelezen-teller is niet
   gedeeld. De admin-endpoints die per-beheerder state schrijven lopen via `huidige_beheerder` —
   defense-in-depth naast de admin-bearer, die immers een token-label levert en geen `userid`.

> **De QA/annotatie-agent is een aparte dienst.** `tools/graph-qa/` heeft een eigen toollaag en
> LLM-config; de werkplek praat er direct mee (SSE). Wettekst komt daar vandaan
> (`GET /v1/artikel`), niet uit deze API.

## Architectuur (app/)

- `config.py` — env-config + projectpaden (PROJECT_ROOT = repo-root).
- `auth.py` — per-client bearer-tokens (erft het MCP-patroon; fail-closed; constant-tijd).
  `require_admin` is een aparte, altijd-verplichte bearer voor `/v1/admin/*` (LLM-/
  gebruikersbeheer). `require_admin` is **async** en accepteert twee bronnen: de statische
  env-admin-tokens (`WETSANALYSE_ADMIN_TOKENS`) én **genereerbare DB-tokens** (`api_tokens.py`,
  beheerd via `/beheer` → API-tokens). Die tokens staan **alleen als sha256-hash** in de
  `api_tokens`-tabel, worden één keer bij aanmaken getoond en zijn intrekbaar; ze voeden o.a. de
  admin-MCP (`tools/wetsanalyse-admin-mcp/`). Env-tokens blijven het bootstrap-pad.
- `user.py`/`users.py` + `routers/auth.py` — de **login-module**: de API is de identiteitsbron van de
  webapp. Inloggen gaat met de **`userid`** (de primaire sleutel van de `users`-tabel); `email` is een
  verplicht, uniek registratiegegeven (geen inlog-identiteit). Wachtwoord-hash via bcrypt, rollen
  `beheerder`/`analist`, optioneel TOTP-2FA versleuteld met dezelfde Fernet-key als de LLM-keys.
  `/v1/auth/*` (achter `require_client`) levert de BFF (Auth.js) login-verificatie (`/verify` op
  userid), de eenmalige eerste-beheerder-registratie (`/setup`, alleen bij lege tabel) en de
  self-service 2FA/account (`/2fa/*`, `/change-password`, identiteit via de vertrouwde
  `X-User-Id`-header van de BFF). De browsersessie zelf leeft in de frontend, niet hier.
- `llm_profile.py` — `LlmProfile`-domeinmodel (Pydantic; benoemde modelprofielen in de DB).
  `profiles.py` — service eroverheen: CRUD, default-beheer, `resolve_config` (profiel → `LlmConfig`,
  ontsleutelt de key, env-fallback) en `ensure_seeded` (seedt bij eerste start één default-profiel uit
  de env). `secrets_crypto.py` — Fernet-versleuteling-at-rest van de API-key (master key uit
  `LLM_CONFIG_SECRET(_FILE)`). De profielen worden beheerd via `/beheer` en gevalideerd met de
  verbindingstest; de QA-agent (graph-qa) heeft een eigen LLM-config en wordt er niet door aangestuurd.
- `db.py` — async SQLAlchemy-Core laag: engine-beheer + de tabeldefinities (`llm_profiles`,
  `users`, `api_tokens`, `annotatie_documenten`, `annotatie_audit`, `gesprekken`,
  `gesprek_berichten`). Portable types
  (`JSON`→`JSONB` op Postgres, `JSON` op SQLite-tests), tz-aware datetimes. `create_all` maakt bij de
  start **ontbrekende tabellen** idempotent aan; `reconcile_schema()` (ook in de lifespan) voegt daarna
  **ontbrekende kolommen** additief toe (`ALTER TABLE … ADD COLUMN`; nooit droppen/typewijzigen) zodat
  een nieuw gedefinieerde kolom op een bestaande productie-tabel geen handmatige migratie vergt. Een
  type-wijziging/drop is nog steeds een bewuste migratie.
- `llm/` — `LLMClient`-protocol + LiteLLM-implementatie (provider = config; `complete()` levert JSON
  conform een schema). `throttle.py` — proces-globale **concurrency-rem** (semafoor) op gelijktijdige
  LLM-calls (`WETSANALYSE_LLM_MAX_CONCURRENCY`); ingesteld in de lifespan. De enige LLM-call in deze
  API is nu de admin-**verbindingstest** (`POST /v1/admin/profiles/{name}/test`).
- `validation.py` — `GELDIGE_JAS_KLASSEN`, `JAS_KLASSEN_VOLGORDE`, `JAS_KLASSE_KLEUREN` en
  `jas_sorteersleutel` (canonieke bron uit de skill-`scripts`) + de
  brongetrouwheid-/schema-helpers. Het annotatiedomein valideert de klasse van een voorgesteld element
  hiertegen.
- `ratelimit.py` — in-process per-client rate limit (dependency) + `QuotaExceeded`.
- `annotatie_contracts.py` — Pydantic-modellen + enums (`AnnotatieDocument`, `AnnotatieElement` met
  `lifecycle`/`beslissingen`/`alternatieven`/`aandacht`/`diff`, `Beslissing`, `AuditRecord`,
  `ReviewReason`). `annotatie_store.py` — `AnnotatieStore` (aparte store op dezelfde engine).
  `routers/annotatie.py` — `/v1/annotatie/*`, per-gebruiker gescopet (`huidige_userid` + `_document_or_404`;
  `require_client` blijft de bearer-poort + audit-herkomst).
  Levenscyclus: document aanmaken → `PUT elementen` (de uitkomst van één agent-ronde) → per element
  een human-decision (approve/edit/reject/comment; edit berekent een `diff`) → `GET audit`.
  **Geen graaf-mutatie** vanuit dit domein.

  **De `review_reason` komt van de server.** Bij een **edit** leidt `_reden_uit_diff` hem af uit de
  diff die de router toch al berekent (één veld → `tekst`/`verkeerde_klasse`/`interpretatie`; meer
  velden, alleen `lid`, of niets → `anders`); een meegestuurde waarde is hooguit een hint en wordt
  overschreven. Die afleiding stond in de browser, en daarmee stond er een reden in het auditspoor
  die de server aannam maar nooit kon toetsen. Bij een **reject** blijft `review_reason` verplicht
  (422 zonder): waaróm iets verworpen wordt staat in geen enkele diff — dat weet alleen de jurist.

  **Herkomst: met welk model is geannoteerd.** graph-qa stuurt per beurt een `run`-event
  (model/provider/agent_versie/critic_rondes/stop_reden); de werkplek geeft dat mee in
  `PUT elementen` en de api legt het vast op het document (`runs[]`, eigen JSON-kolom), op elk
  agent-element dat die ronde maakte of herzag (`geproduceerd_door`) én in het auditdetail. Een
  ronde **zonder** run wist niets — een oudere client mag het spoor niet uitgummen. Documenten van
  vóór deze registratie tonen in de export expliciet "onbekend (vóór registratie)".

  **Exporteren** (`annotatie_export.py`): `POST /documenten/{slug}/export?formaat=pdf|csv|json`
  bouwt één canonieke `ExportDocument` (document + telling + elementen mét volledig spoor + het
  hele auditlog) en serialiseert die drie keer. Werkt in elke fase; een document dat nog in review
  is draagt de telling "te beoordelen" in de kop. De PDF (reportlab) is de JAS-tabel uit
  `docs/wetsanalyse/wa-table.png`: de klassecel draagt de labelkleur uit
  `validation.JAS_KLASSE_KLEUREN` (canoniek uit de skill; `test_jas_kleuren_drift.py` bewaakt dat
  `frontend/lib/jas.ts` dezelfde waarden draagt). De **wettekst zit niet in deze api** — de
  werkplek stuurt de leden mee in de body; ontbreken ze, dan blijft dat blok weg in plaats van dat
  er iets gereconstrueerd wordt.

  **Afronden is een expliciete handeling.** `POST /documenten/{slug}/status` zet `geaccordeerd` of
  weer `in_review` (promoveren hoort bij het latere graaf-schrijfpad en kan hier niet). Dat loopt
  door `muteer_document` — het enige pad met lock én eigenaarscheck; de losse `zet_status` zonder
  die check is daarom weg. Zonder dit endpoint stond elk document eeuwig op `in_review` en liep de
  werkvoorraad van de jurist nooit leeg.

  **Een oordeel vergrendelt — heropenen is een handeling.** `geaccordeerd` betekende eerder niets:
  er kon daarna nog van alles bij, af en overheen, en een goedgekeurd element kon onbeperkt opnieuw
  beslist worden. Nu zijn er twee sloten, allebei 409 met een leesbare reden:
  - **Element** — in `human_approved`/`rejected` (`VERGRENDELDE_LIFECYCLES`) weigert `beslissing`
    een `edit`/`reject`/`approve`. Alleen `comment` (een kanttekening wijzigt de annotatie niet) en
    het nieuwe **`heropen`** komen erlangs. `heropen` zet het element terug op `critic_checked` (als
    de Critic er al naar keek, anders `voorgesteld`) en landt als eigen regel in `beslissingen` én
    als `beslissing-heropen` in de audit — een teruggedraaid akkoord hoort zichtbaar te zijn.
    `edited` vergrendelt bewust **niet**: een klasse wijzigen en er daarna een toelichting bij typen
    is één doorlopende handeling. Een **eigen markering** ook niet: die is `human_approved` bij het
    aanmaken, dus gemaakt in plaats van beoordeeld — het slot beschermt een review-oordeel over een
    voorstel van de agent.
  - **Document** — bij `status = geaccordeerd` weigeren `PUT elementen` (ook een agent-ronde),
    `POST elementen`, `DELETE element` en `beslissing` (`_afgerond`). `POST .../status` is de enige
    uitweg, en dus ook de enige ingang.

  De toets staat binnen de mutatie-callback, dus binnen dezelfde row-lock als de schrijfactie —
  anders glipt er tussen lezen en schrijven alsnog een wijziging langs een akkoord heen. Daarom
  krijgt `beslis_op_element`'s `toepassen` het hele document mee en mag het een sentinel teruggeven.

  **De lijst draagt de werkvoorraad.** `GET /documenten` levert per document ook `te_beoordelen`,
  `per_aandacht`, `per_klasse` (de JAS-kleurstrip in de UI), `laatste_model` en een `citeertitel`
  met terugval op `werkgebied`/`bwbId` (`annotatie_export.weergavenaam`). De telling komt uit
  dezelfde `tel_elementen` als de export — twee tellingen naast elkaar spreken elkaar vroeg of laat
  tegen, en juist die telling stuurt waar de jurist heen gaat.

    **`PUT elementen` is een MERGE, geen vervanging.** De agent kan meerdere rondes draaien
  (annoteerder ⇄ Critic) en de jurist werkt in hetzelfde document; vervangen wiste eerder alle
  beslissingen, levenscyclus en element-id's. Matchen gaat op `id`, met de genormaliseerde tekst +
  lid als terugval voor clients zonder id. Een element waar de jurist aan te pas kwam (`herkomst ==
  "mens"` of met beslissingen) is **inhoudelijk bevroren**: de agent mag er alleen nog een
  Critic-oordeel bij zetten. Agent-elementen die in de nieuwe ronde ontbreken worden ingetrokken.
  Optioneel `If-Match` tegen de `ETag` uit de respons → 412 bij een tussentijdse wijziging.

  **Een edit mag het fragment verplaatsen.** `Wijziging` draagt naast `klasse`/`tekst`/`toelichting`/
  `lid` een optioneel `anker`: kort de jurist een markering in of breidt hij hem uit, dan schuift de
  plek mee. Verandert de tekst zonder dat er een anker meekomt, dan wordt het oude **gewist** — een
  anker dat over het oude fragment gaat laat de markering na herladen naar een ander voorkomen
  springen. Het anker staat niet in de `diff` (machinerie, geen inhoudelijke wijziging) maar wel als
  `anker_verplaatst` in het auditdetail.

  **Herkomst is gesplitst.** `herkomst` = wie het element aanmaakte (onveranderlijk), `gewijzigd_door`
  = wie het daarna aanpaste. Een edit door de jurist maakt van een agent-element dus geen
  mens-element. Rijen van vóór die splitsing worden lazy gerepareerd door een `model_validator`.

  **Audit per element.** Naast de ronde-samenvatting (`elementen-voorgesteld`) schrijft elke ronde
  `element-voorgesteld` / `element-herzien` (met diff) / `element-ingetrokken` / `critic-suggestie`,
  elk mét element-id en inhoud — anders is een ronde achteraf niet te reconstrueren. `GET audit` is
  daarom gepagineerd.
- `routers/admin.py` — **`/v1/admin/*`** achter `require_admin`: modelprofielen-CRUD (write-only
  API-key, `api_key_set` nooit de key zelf), default zetten, verbinding testen; het gebruikersbeheer
  (`/users` CRUD, de laatste actieve beheerder is beschermd); en de genereerbare API-tokens
  (`/api-tokens`).
- `routers/catalog.py` — de niet-admin keuzelijst: `GET /v1/profiles` (alleen naam + default).
- `main.py` — routers + `/health` (liveness) + `/ready` (alleen booleans). De lifespan doet DB-init
  (met bounded connect-retry bij cold start), profiel-seeding en het instellen van de LLM-throttle.

## Observability

`app/observability.py` configureert **gestructureerde JSON-logging** (mirror van de MCP-logger:
`ts/niveau/categorie/bericht/…velden`, secret-redactie, `LOG_LEVEL`/`LOG_FORMAT`) plus **OpenTelemetry**
(traces/metrics/logs), gated op `OTEL_EXPORTER_OTLP_ENDPOINT` — leeg = no-op, alleen logs. `setup()`
draait vroeg in `main.py`; `RequestContextMiddleware` (pure ASGI, veilig voor SSE) zet een
`X-Request-Id` en logt per request. `get_tracer()`/`get_meter()` geven no-op-shims terug zonder de
`otel`-extra, dus code mag onvoorwaardelijk spans/metrics maken. Nooit tokens/secrets/prompt-inhoud
loggen. Zie `docs/observability.md`.

## Garanties (niet aan tornen)

- **Per-gebruiker isolatie.** Elk annotatie-document én elk **gesprek** is per-gebruiker gescopet via
  de vertrouwde `X-User-Id`-header — 404 op andermans slug/id (lekt niet). De dependency is
  **`actieve_userid`** (`routers/auth.py`): die controleert bovendien dat het account nog bestaat en
  actief is, met een cache van 30s. `huidige_userid` leest alleen de header en is er voor endpoints
  die hun eigen bewijs vragen (wachtwoord, 2FA-code). Deactiveren/verwijderen bijt meteen doordat de
  admin-router `vergeet_actief()` aanroept.
- **De admin-laag is altijd auth-plichtig.** `/v1/admin/*` heeft geen `AUTH_REQUIRED`-bypass; zonder
  admin-tokens geeft alles 401. De plaintext-API-key komt nooit terug in een respons (alleen
  `api_key_set`); het opslaan vereist een geconfigureerde Fernet-master-key.
- **Append-only auditlog.** Elke annotatie-actie schrijft auditregels; de tijdlijn is `ORDER BY id`.
- **Eén schrijfpad naar `elementen`.** Alles loopt via `AnnotatieStore.muteer_document` met
  `with_for_update()`. Er stond hier ook een `vervang_elementen` zónder lock; die is weg — een
  destructief pad dat blijft rondslingeren wordt vroeg of laat gebruikt.
- **JAS-klassen zijn canoniek.** Een voorgesteld element wordt gevalideerd tegen
  `validation.GELDIGE_JAS_KLASSEN` — verzin er geen bij.
- **Secrets zijn bestanden.** Alle secrets (admin-tokens, client-tokens, DB-credentials, Fernet-key)
  staan als bestanden op de host (`*_FILE`-patroon) — nooit als plain env var.

## Lokaal draaien

### 1. Secrets aanmaken (eenmalig)

Maak `api/secrets/` aan (gitignored) en vul:

```powershell
# Vanuit de projectroot:
mkdir api\secrets
[IO.File]::WriteAllText("$PWD\api\secrets\api_tokens",       "lokaal:<zelfgekozen-token>")
# LLM-beheer (admin) — optioneel lokaal:
[IO.File]::WriteAllText("$PWD\api\secrets\admin_tokens",      "admin:<zelfgekozen-admin-token>")
[IO.File]::WriteAllText("$PWD\api\secrets\llm_config_secret", "<fernet-key>")
```

Fernet-master-key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

### 2. `.env` aanmaken

Kopieer `.env.example` naar `.env` en vul in (Azure AI Foundry-config voor de verbindingstest/seed):

```
LLM_PROVIDER=azure_ai
LLM_MODEL=claude-sonnet-4-6
LLM_API_BASE=https://<resource-naam>.services.ai.azure.com   # geen /models achteraan
LLM_API_KEY_FILE=secrets/llm_api_key
WETSANALYSE_API_TOKENS_FILE=secrets/api_tokens
WETSANALYSE_ADMIN_TOKENS=admin:<zelfgekozen-admin-token>
LLM_CONFIG_SECRET=<fernet-key>   # nodig om API-keys via de admin-UI op te slaan
```

### 3. Server starten

```bash
cd api
uv sync --extra llm --extra dev
uv run --env-file .env uvicorn app.main:app --reload --port 3000
```

`uv run` laadt `.env` **niet** automatisch — de `--env-file .env` vlag is verplicht.
Swagger: `http://localhost:3000/docs` · health: `/health` · ready: `/ready`

Lokaal heb je ook een **PostgreSQL** nodig (de opslag). Snel:
`docker run -d -p 5432:5432 -e POSTGRES_USER=wetsanalyse -e POSTGRES_PASSWORD=wetsanalyse -e POSTGRES_DB=wetsanalyse postgres:16`
en zet `DATABASE_URL=postgresql+asyncpg://wetsanalyse:wetsanalyse@localhost:5432/wetsanalyse`. De
tabellen worden bij de start aangemaakt (`db.create_all` in de lifespan).

### 4. Testen

```bash
uv run pytest -q               # unit-tests (fakes; geen netwerk)
```

## Deployment

**Postgres draait in productie als APARTE stack** (`deploy/postgres/`), niet in de api-stack — zo
recreate een api-image-redeploy de DB nooit. De API verbindt cross-stack op `postgres:5432` met een
**bounded connect-retry** bij cold start (`main.py` → `_init_db_met_retry`, knoppen
`WETSANALYSE_DB_CONNECT_RETRIES`/`_BACKOFF`). De host-secrets (incl.
`postgres_user`/`postgres_password`/`database_url`) zijn gedeeld via `SECRETS_DIR`. Die stack maakt
óók het gedeelde netwerk `wetsanalyse_internal` waar deze stack op joint — deploy hem dus eerst; zie
`deploy/postgres/README.md`.

Docker-image + Portainer-stack (`docker-compose.yml`). De stack publiceert een hostpoort
(`HOST_PORT`, default 8081) omdat NPM op een andere host draait en geen docker-netwerk deelt; die
poort is alleen nodig als de API van buiten bereikbaar moet zijn (bv. voor de admin-MCP op
`api.wetsanalyse.example`). De frontend praat server→server over het interne netwerk. De dienst is
**horizontaal veilig** te schalen (stateless request-afhandeling; de opslag is de gedeelde DB). De
containers draaien **non-root** en **PostgreSQL draait met authenticatie**. Alle secrets staan als
bestanden op de host (`*_FILE`-patroon). Build vanaf de **projectroot**:
`docker build -f api/Dockerfile -t wetsanalyse-api .` (de image heeft de skill-`scripts` nodig voor
de canonieke JAS-klassenlijst — `validation.py` laadt `validate_analyse.py` op runtime in).

### Secrets op de host (eenmalig, vóór de eerste stack-start)

De stack mount één host-map op `/run/secrets` in zowel de **api**- als de **postgres**-container. Het
pad komt uit de **GitHub Actions repo-variabele `SECRETS_DIR`**; de CI geeft die door aan Portainer.
Zet `SECRETS_DIR` exact op je host-pad, bijvoorbeeld `/var/lib/wetsanalyse-api/secrets`.

Bestanden op de **host zelf** (niet via een laptop-mount):

```bash
SECRETS_DIR=/volume1/docker/wetsanalyse-api/secrets
sudo mkdir -p "$SECRETS_DIR"

echo -n "<llm-api-key>"      | sudo tee "$SECRETS_DIR/llm_api_key"      > /dev/null  # verbindingstest/seed
echo -n "id1:tok1,id2:tok2"  | sudo tee "$SECRETS_DIR/api_tokens"        > /dev/null

# Admin-laag: aparte admin-tokens + Fernet-master-key voor key-versleuteling.
echo -n "admin:adm-tok"      | sudo tee "$SECRETS_DIR/admin_tokens"      > /dev/null
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" \
    | sudo tee "$SECRETS_DIR/llm_config_secret" > /dev/null

# PostgreSQL-auth: credentials + de connection string die de API gebruikt.
PG_USER=wetsanalyse
PG_PASS="$(openssl rand -hex 24)"
echo -n "$PG_USER" | sudo tee "$SECRETS_DIR/postgres_user" > /dev/null
echo -n "$PG_PASS" | sudo tee "$SECRETS_DIR/postgres_password" > /dev/null
echo -n "postgresql+asyncpg://$PG_USER:$PG_PASS@postgres:5432/wetsanalyse" \
    | sudo tee "$SECRETS_DIR/database_url" > /dev/null

# De containers draaien non-root (postgres uid 999, api uid 10001). Gebruik 644 (NIET 600).
sudo chmod 755 "$SECRETS_DIR"
sudo chmod 644 "$SECRETS_DIR"/*
```

**Postgres-volume.** De postgres-image initialiseert de user/db alleen bij een *lege* data-dir. Wil je
verse credentials, verwijder het volume; wil je bestaande data behouden, laat de credentials (en de
`database_url`-secret) ongewijzigd.

### Troubleshooting deploy

- **API-log: kan niet verbinden met `localhost:5432` / `OperationalError`** — de `database_url`-secret
  werd niet gelezen (`/run/secrets` wijst naar de verkeerde map) → check `vars.SECRETS_DIR` en
  `docker inspect wetsanalyse-api --format '{{json .Mounts}}'`.
- **Postgres-log: `/run/secrets/postgres_password: Permission denied`, container `unhealthy`** —
  secret-bestanden niet leesbaar voor uid 999/10001 → `sudo chmod 644` op de host.

## Misbruik-/kostenbeheersing

Knoppen via env (0 = uit): `WETSANALYSE_RATE_LIMIT_MAX`/`_WINDOW` (per-client request-rate → 429),
`WETSANALYSE_ADMIN_TEST_RATE_MAX`/`_WINDOW` (aparte, krappe limiet op
`POST /v1/admin/profiles/{name}/test` → 429; die doet een betaalde LLM-call achter alleen het
admin-token — de testfout is gesaniteerd: een vaste melding in de respons, de ruwe provider-fout alleen
in het server-log), `WETSANALYSE_LLM_MAX_CONCURRENCY` (globaal plafond op gelijktijdige LLM-calls) en
`WETSANALYSE_LLM_TIMEOUT_S` (harde wandklok-timeout per LLM-call). De in-process rate-limiter is
begrensd (sweep + harde cap op het aantal sleutels, fail-closed) zodat aanvaller-gekozen sleutels via
de publieke login-route het geheugen niet vol pompen.

## Roadmap (nog niet gebouwd)

- **Externe IdP/OIDC.** De API is nu zelf de identiteitsbron (userid + wachtwoord, optioneel TOTP);
  federatie met een externe IdP is nog niet gebouwd.
- **Herbouw van de bredere agentische analyse-flow.** De agentische **act-2-annotatie draait al** in
  graph-qa (de annotatie-worker: ophaal → annoteer → Critic → advance). Rest: **begrippen (activiteit
  3)** en de **RegelSpraak-formalisering** — eerder uit de engine/webapp/skill verwijderd om later op
  agentische basis te herbouwen (buiten deze API).
