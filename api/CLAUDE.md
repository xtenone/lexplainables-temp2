# CLAUDE.md — wetsanalyse-api

Headless API-backend die de Wetsanalyse (JAS) orchestreert — een kerncomponent van het agent-platform,
een zelfstandige, Dockeriseerbare dienst die je via HTTP (Postman/Swagger) bevraagt en die de webapp
(analyse-webapp + werkplek) bedient. Lees ook de projectroot-`CLAUDE.md` en
`.claude/skills/wetsanalyse/SKILL.md`: de (legacy) skill is de **gedeelde inhoudelijke bron**
(references/scripts) die deze service op runtime hergebruikt.

## Dragend principe

De **orchestrator bezit de review-lus en de state**; het **LLM doet per stap één begrensde taak**
("geef JSON conform schema"). **Stap 1 (ophalen) is deterministisch via de MCP** — geen LLM-tool-
calling. De **jobstore is PostgreSQL** (SQLAlchemy async/asyncpg): één `projects`-rij per analyse met de
state + telemetrie en het `rapport` (JSONB-kolom); de immutabele analyse-rondes + feedback staan in een
aparte `rondes`-tabel. De API schrijft *niet* naar de `analyses/<id>/werk/`-disk; de
disk-interoperabiliteit met de lokale skill staat op de roadmap, niet in de huidige flow.

**Act2-only afronden + act3 on-demand (gebouwd).** Bij het act-2-checkpoint accepteert `feedback`
naast `akkoord`/`wijzigingen` ook **`akkoord-afronden`** (alleen op activiteit 2, zonder
opmerkingen): de analyse gaat dan rechtstreeks naar `klaar` met **`scope: "act2"`** — een rapport
zonder begrippen/afleidingsregels. `POST /v1/projects/{id}/act3` voert activiteit 3 later alsnog
uit: `claim_act3` (`klaar → act3_runt`, scope terug naar `"volledig"`) → `run_act3_fase`, waarna
het rapport langs het normale pad wordt herbouwd. De RegelSpraak-fase is op zo'n act2-only-analyse
geblokkeerd (409 "voer eerst activiteit 3 uit").

**RegelSpraak-vervolgfase (gebouwd).** Naast de JAS-analyse kent een project een **on-demand**
formaliseringsfase naar RegelSpraak/GegevensSpraak (de skill `regelspraak`). `POST /v1/projects/{id}/regelspraak`
(alleen vanuit `klaar` met `scope: "volledig"`; optioneel body `{review}`) start `WetsanalyseEngine.run_regelspraak`: claim
`klaar → rs_gegevens_runt`, dan twee stappen met elk een review-checkpoint
(`rs-gegevens` → `wacht-op-review-rs-gegevens` → `rs-regels` → `wacht-op-review-rs-regels` → `rs_bouwt`
→ `rs_klaar`). De stappen leven in `engine/regelspraak_prompts.py` + `engine/regelspraak_steps.py` (zelfde
patroon als `prompts.py`/`steps.py`; references uit `.claude/skills/regelspraak/references/`), de validatie
in `validation.regelspraak_schema_check`/`regelspraak_brongetrouwheid_check` (herkomst is hard). De
ingest-context (`_rs_gegevens_context`) trimt het rapport tot werkgebied + begrippen +
afleidingsregels + per bron de brondefinities én de via `markering_ids` gerefereerde markeringen
(`gekoppelde_markeringen`) — zelfde trim als de skill-ingest; de koppeling regel ↔ declaratie loopt
op **begrip-id**, niet op naam. Het
resultaat is een **eigen artefact** `projects.regelspraak` (JSONB, naast `rapport`), uitleesbaar via
`GET /v1/projects/{id}/regelspraak` (+ `.rs`/`.md`-export via `engine/render_regelspraak.py`). De rondes
delen de `rondes`-tabel met activiteit-codes `rs-gegevens`/`rs-regels`. `feedback` en `retry` kennen de
rs-states; `current_activiteit` draagt de rs-code zodat retry de fase herkent.

**De analyse-eenheid is het werkgebied (kennisdomein), niet één artikel.** Een project draagt een
`bronnen`-lijst (`StartRequest.bronnen[]`; elke bron = `bwbId`+`artikel`+`lid?`) — opgeslagen als
`projects.bronnen` JSON-kolom (vervangt de oude scalar `bwbId/artikel/lid`). De orchestrator haalt in
`_fase_start` per bron de tekst op en genereert **activiteit 2 per bron** (geaggregeerd in
`Analyse2.bronnen[]`); **activiteit 3 is werkgebied-breed én twee-staps binnen één ronde** —
stap 3a genereert de gedeelde, ontdubbelde `begrippen`, stap 3b bouwt de `afleidingsregels`
**met die begrippen als bouwstenen** (uitvoer/invoer/parameters/voorwaarden verwijzen per
`begrip_id`; ontbrekende bouwstenen komen als `nieuwe_begrippen` terug en worden in de merge
deterministisch doorgenummerd — `steps.genereer_act3`). Beide stappen tellen als één ronde met
één review-checkpoint. Een optioneel aangeleverde **begrippenlijst**
(`StartRequest.begrippenlijst`, suggestief) voedt 3a; elk begrip registreert dan zijn `herkomst`
(hergebruikt/aangepast/nieuw). Eén bron is het
triviale geval; het rapport heeft de vorm `{werkgebied, bronnen[], begrippen, afleidingsregels, …}`.

## Architectuur (app/)

- `config.py` — env-config + projectpaden (PROJECT_ROOT = repo-root).
- `contracts.py` — Pydantic-modellen (1-op-1 met `references/review-checkpoints.md`) + `Job`/state machine.
  Het act-3-contract is **begrip-id-gebouwd**: `Afleidingsregel` draagt `uitvoer{begrip_id,toelichting}`,
  `invoer[]`, `parameters[]` (waarde/eenheid/geldigheid/vindplaats) en `voorwaarden[]`
  (tekst/begrip_ids/verbinding EN|OF); `Begrip` draagt `is_interpretatie`, `relaties`,
  `markering_ids` (koppeling naar act-2) en `herkomst`. `StartRequest.begrippenlijst` accepteert
  max 300 `BegripInvoer`-items (suggestieve bestaande begrippenlijst); `Job` draagt
  `omschrijving`/`scope`/`begrippenlijst`.
  `JobSummary` draagt ook de observerende `current_fase`(`_sinds`) + telemetrie, zodat het dashboard al
  bij de eerste render compleet is zonder per-job na te laden.
- `auth.py` — per-client bearer-tokens (erft het MCP-patroon; fail-closed; constant-tijd).
  `require_admin` is een aparte, altijd-verplichte bearer voor `/v1/admin/*` (LLM-beheer +
  gebruikersbeheer). `require_admin` is **async** en accepteert twee bronnen: de statische
  env-admin-tokens (`WETSANALYSE_ADMIN_TOKENS`) én **genereerbare DB-tokens** (`api_tokens.py`,
  beheerd via `/beheer` → API-tokens). Die tokens staan **alleen als sha256-hash** in de
  `api_tokens`-tabel (hoog-entropie → geen bcrypt), worden één keer bij aanmaken getoond en zijn
  intrekbaar; ze voeden o.a. de admin-MCP (`tools/wetsanalyse-admin-mcp/`). Env-tokens blijven het
  bootstrap-pad. `user.py`/`users.py` + `routers/auth.py` vormen de **login-module**: de API is
  de identiteitsbron van de webapp. Inloggen gaat met de **`userid`** (de primaire sleutel van de
  `users`-tabel); `email` is een verplicht, uniek registratiegegeven (geen inlog-identiteit).
  Verder: wachtwoord-hash via bcrypt, rollen `beheerder`/`analist`, optioneel TOTP-2FA versleuteld
  met dezelfde Fernet-key als de LLM-keys. `/v1/auth/*` (achter `require_client`) levert de BFF
  (Auth.js) login-verificatie (`/verify` op userid), de eenmalige eerste-beheerder-registratie
  (`/setup`, alleen bij lege tabel) en de self-service 2FA/account (`/2fa/*`, `/change-password`,
  identiteit via de vertrouwde `X-User-Id`-header van de BFF). De browsersessie zelf leeft in de
  frontend, niet hier.
- `llm_profile.py` — `LlmProfile`-domeinmodel (Pydantic; benoemde modelprofielen in de DB; vervangt de
  vroegere hardcoded `Settings.model_profiles`). `profiles.py` — service eroverheen: CRUD,
  default-beheer, `resolve_config` (profiel → `LlmConfig`, ontsleutelt de key, env-fallback) en
  `ensure_seeded` (seedt bij eerste start één default-profiel uit de env). `secrets_crypto.py` —
  Fernet-versleuteling-at-rest van de API-key (master key uit `LLM_CONFIG_SECRET(_FILE)`).
  `usage.py` — read-only token-verbruik-aggregatie over `provenance`.
- `db.py` — async SQLAlchemy-Core laag: engine-beheer + de tabeldefinities (`projects`, `rondes`,
  `llm_profiles`, `wet_catalogus`, `users`, `app_settings`, `llm_calls`). Portable types
  (`JSON`→`JSONB` op Postgres, `JSON` op SQLite-tests), tz-aware datetimes (`aware()` normaliseert
  het naïeve SQLite-resultaat naar UTC). `reconcile_schema()` voegt nieuwe kolommen idempotent toe
  bij de start (o.a. `scope` en `begrippenlijst` op `projects`).
- `jobstore.py` — `JobStore`-Protocol (opslag-abstractie) + `IdConflict`. `postgres_store.py` —
  de SQLAlchemy/PostgreSQL-implementatie: gerichte kolom-writes, **ronde-immutabiliteit**, client-scoping,
  en de **state-CAS** (`claim`/`verleng_lease`/`lijst_verlopen_running`/`markeer_lease_loze_running`) via
  één atomair `UPDATE … RETURNING`. `set_current_fase()` is een **owner-fenced** update dat alléén het
  observerende `current_fase`(`_sinds`) bijwerkt en `updated`, `state` en `lease` ongemoeid laat (geen
  state-CAS, geen lease-bump).
- `project.py` — het `Project`-domeinmodel (Pydantic; state + telemetrie + `rapport`; de rondes/feedback
  leven in de aparte `rondes`-tabel; `owner`/`lease_until` voor de concurrency-claim, alleen door
  `claim`/heartbeat beheerd — nooit via `save_job`).
  Daarnaast twee **observerende** velden — `current_fase` + `current_fase_sinds` — die de fijnmazige
  functiestap binnen een `*-runt`/`bouwt`-state tonen (bv. `llm-generatie`, `verwijzingen-volgen`,
  `brongetrouwheid-check`). Dit is **geen** state-machine-veld: het staat los van de state-CAS en heeft
  geen control-flow-effect; bij review/terminal/fout gaat het op `None`.
- `wettenbank.py` — MCP-client; lege/fout-respons → `WettenbankError` (nooit doorgaan met lege context).
- `validation.py` — **schema** (skill-`check_activiteit_2/3`: FOUTEN blokkeren — auto-correctie,
  anders `fout`, ook in `review:false`; WAARSCHUWINGEN reizen mee als context) vs **hard**
  (brongetrouwheid: citaat letterlijk in leden-tekst na normalisatie, `vindplaats`/`bronreferentie`
  verplicht). Voor act 3 krijgt `schema_check` context mee: de goedgekeurde act-2 activeert de
  dekkings- en markering-id-checks, de aangeleverde begrippenlijst de herkomst-checks. Meldingen
  die de harde check al dekt (citaat/vindplaats) worden uit de skill-fouten/-waarschuwingen
  gefilterd, zodat per concern één — de genormaliseerde — melding overblijft.
- `ratelimit.py` — in-process per-client rate limit (dependency) + `QuotaExceeded` (beleidsgrenzen).
- `llm/` — `LLMClient`-protocol + LiteLLM-implementatie (provider = config; output-strategie + parse).
  `throttle.py` — proces-globale **concurrency-rem** (semafoor) op gelijktijdige LLM-calls
  (`WETSANALYSE_LLM_MAX_CONCURRENCY`), tegen zelf-veroorzaakte rate-limits; ingesteld in de lifespan.
  `capture.py` — **LLM-call-capture**: een `CapturingLLMClient`-decorator die élke `complete()`
  (incl. auto-correctie-herhalingen, de verwijzing-inventaris en gefaalde calls) best-effort vastlegt
  in `llm_calls` (system/user-prompt + ruwe respons + metadata) wanneer de runtime-toggle
  `capture_llm_calls` aan staat. De call-context (project/activiteit/ronde/poging/fase) komt uit een
  `ContextVar` die de orchestrator rond elke generatie zet; `_llm_for` wrapt de client. Capture is
  **default uit** en mag de analyse nooit breken. De toggle leeft in `app_settings.py` (key/value met
  korte TTL-cache) en is beheerbaar via `/v1/admin/settings` + het /beheer-scherm. Inzien per analyse:
  `GET /v1/admin/projects/{slug}/llm-calls`.
- `engine/` — `prompts.py` (references verbatim + canonieke JAS-lijst uit validation), `steps.py`
  (LLM-stap + merge met brongetrouwe MCP-basis), `retry.py` (bounded backoff op transiënte
  LLM/MCP-fouten; honoreert **`Retry-After`** bij een 429, met plafond + jitter), `orchestrator.py`
  (state machine, auto-correctie, 6-rondencap, startup-reconciliatie, retry, quota/budget-checks).
  **Activiteit 2 is twee-fase** voor de cross-referenties: een verwijzing-inventaris
  (`steps.inventariseer_verwijzingen` / `prompts.act2_inventaris_prompt`) → begrensde fetch-lus
  (`orchestrator._volg_verwijzingen` + `wettenbank.parse_jci`) → de volledige act-2 met de
  opgehaalde verwezen tekst als context (zie §Roadmap → Cross-referenties).
  **Activiteit 3 is twee-staps** binnen één ronde: `prompts.act3_begrippen_prompt` (3a) →
  `prompts.act3_regels_prompt` (3b, met de 3a-begrippen als bouwstenen); `steps.genereer_act3`
  nummert `nieuwe_begrippen` deterministisch door en remapt de regel-referenties. Beide
  act-3-prompts dragen de volledige leden-tekst plus de omschrijving/analysefocus/begrippenlijst
  (als onbetrouwbare data geframed). De orchestrator kent daarnaast `claim_act3`/`run_act3_fase`
  (act3 on-demand op een act2-only-`klaar`). `_set_fase()` schrijft
  best-effort de observerende `current_fase` weg op breekpunten in `_genereer()`/`_bouw_rapport()`
  (geen control-flow-effect; faalt stil) en wist 'm bij review/terminal/fout.
- `routers/projects.py` + `main.py` — de kanonieke resource onder **`/v1/projects`** (client-gescopet,
  `response_model`s, paginatie, SSE), incl. `POST /{id}/act3` (activiteit 3 on-demand; 409 als de
  analyse niet act2-only-`klaar` is), `/health` (liveness), `/ready` (alleen booleans). De per-project
  SSE (`/{id}/events`) is verrijkt met `current_fase`; daarnaast is er een **aggregate-stream**
  `GET /v1/projects/events` (client-gescopet, één diff-emit per gewijzigd project + `removed`-events)
  die het live dashboard én de projectenlijst voedt. Die route is **bewust vóór `/{project_id}`**
  geregistreerd zodat `events` niet als project-id wordt opgevat; `_dashboard_poll` zit apart voor
  testbaarheid. Beide SSE-loops sturen bij een stille poll een `: keep-alive`-heartbeat, anders breekt
  de undici-fetch in de Next.js-BFF de stream met `UND_ERR_BODY_TIMEOUT`.
- `wet_catalog.py` — `WetCatalogus`-domeinmodel (Pydantic, persistentie via de store; BWB-id +
  leesbare naam). `wetten.py` — service
  eroverheen: CRUD + `resolve_naam` (officiële citeertitel via `wettenbank_structuur`). De catalogus
  is een **gemak voor de UI-dropdown, niet dwingend**: de orchestrator dwingt geen lidmaatschap af en
  een willekeurige BWB-id blijft geldig. De wet-naam in het rapport komt los hiervan uit de MCP.
- `routers/admin.py` — **`/v1/admin/*`** achter `require_admin`: modelprofielen-CRUD
  (`/profiles`, write-only API-key, `api_key_set` nooit de key zelf), default zetten, verbinding
  testen, `/usage` (token-verbruik), de wet-catalogus (`/wetten` CRUD + `/wetten/{bwbId}/resolve`)
  en het gebruikersbeheer (`/users` CRUD: aanmaken met eenmalig tijdelijk wachtwoord, rol/active
  wijzigen, wachtwoord resetten; de laatste actieve beheerder is beschermd). Ook de runtime-instellingen
  (`GET/PUT /settings`, o.a. de `capture_llm_calls`-toggle) en de vastgelegde LLM-calls per analyse
  (`GET /projects/{slug}/llm-calls`).
  De engine bouwt per analyse de LLM-client uit het profiel van de job, dus runtime-wijzigingen
  werken zonder redeploy. De niet-admin keuzelijsten (`/v1/profiles`, `/v1/wetten`) staan in
  `routers/catalog.py` zodat de frontend de dropdowns zonder admin-token vult — plus de twee
  structuur-endpoints voor het analyseformulier: `GET /v1/wetten/{bwbId}/structuur`
  (afgeplatte artikellijst → artikel-autocomplete) en `GET /v1/wetten/{bwbId}/artikelen/{artikel}`
  (leden + opschrift + snippet → lid-keuze), gevoed door `wet_info.py` (TTL-cache over de MCP).

## Annotatie-domein (wetsanalyse-workbench)

Een **vers, apart domein** voor de wetsanalyse-workbench (agent annoteert → mens reviewt) — bewust
**los** van de analyse-job/skill-contracten (geen `Markering`/`projects`/`rondes`). Zie
`docs/wetsanalyse-workbench/PLAN.md`. Onderdelen:

- `annotatie_contracts.py` — verse Pydantic-modellen + enums (`AnnotatieDocument`, `AnnotatieElement`
  met `lifecycle`/`beslissingen`/`alternatieven`/`aandacht`/`diff`, `Beslissing`, `AuditRecord`,
  `ReviewReason`). Review-klaar: velden voor latere fasen zitten er vanaf het begin in.
- `db.py` — twee nieuwe tabellen: `annotatie_documenten` (huidige staat; elementen als JSON) en
  `annotatie_audit` (**append-only** event-log; alleen inserts, tijdlijn = `ORDER BY id`). Nieuwe
  tabellen → `create_all` maakt ze aan (geen `reconcile_schema` nodig).
- `annotatie_store.py` — `AnnotatieStore` (aparte store op dezelfde engine; niet de `JobStore`).
- `routers/annotatie.py` — `/v1/annotatie/*`, client-gescopet (`require_client` + `_document_or_404`
  → 404 bij andermans document). Levenscyclus: document aanmaken → `PUT elementen` (voorstellen van de
  agent; klasse gevalideerd tegen `validation.GELDIGE_JAS_KLASSEN`) → per element een human-decision
  (approve/edit/reject/comment; edit/reject vereisen `review_reason`; edit berekent een `diff`) →
  `GET audit`. Elke actie schrijft één auditregel. **Geen graaf-mutatie** (dat is een latere fase).

## Observability

`app/observability.py` configureert **gestructureerde JSON-logging** (mirror van de MCP-logger:
`ts/niveau/categorie/bericht/…velden`, secret-redactie, `LOG_LEVEL`/`LOG_FORMAT`) plus **OpenTelemetry**
(traces/metrics/logs), gated op `OTEL_EXPORTER_OTLP_ENDPOINT` — leeg = no-op, alleen logs. `setup()`
draait vroeg in `main.py`; `RequestContextMiddleware` (pure ASGI, veilig voor de SSE-streams) zet een
`X-Request-Id` en logt per request. De orchestrator wikkelt elke fase (`_guard`) in een span met
metrics (fase-duur, fase-fouten per `FoutKlasse`, LLM-tokens).
`get_tracer()`/`get_meter()` geven no-op-shims terug zonder de `otel`-extra, dus code mag
onvoorwaardelijk spans/metrics maken. De `otel`-extra zit in de productie-image (`Dockerfile`:
`uv sync --extra otel`). Nooit tokens/secrets/prompt-inhoud loggen. Zie `docs/observability.md`.

## Garanties (niet aan tornen)

- HARD brongetrouwheid faalt → job naar `fout`, **ook in `review:false`**. Nooit stil `klaar`.
- Schema-FOUTEN (ongeldige JAS-klasse, dangling `begrip_id`, …) blokkeren eveneens: eerst
  auto-correctie, blijven ze staan → `fout` (gelijke handhaving met het skill-spoor, waar
  `validate_analyse.py` met exit 2 blokkeert). Waarschuwingen blokkeren niet.
- Auto-correctie is **geen ronde**: her-genereren binnen één ronde vóór het wegschrijven.
- Feedback alleen via de API en alleen in een `wacht-op-review-*`-state (anders 409);
  `akkoord-afronden` alleen op activiteit 2 en zonder opmerkingen (contract-validatie).
- Brongetrouwe velden (`leden`, `bronreferentie`, `versiedatum`, `pad`) komen **uit de MCP**, niet uit het LLM.

## Lokaal draaien

### 1. Secrets aanmaken (eenmalig)

Maak `api/secrets/` aan (gitignored) en vul de drie bestanden:

```powershell
# Vanuit de projectroot:
mkdir api\secrets
[IO.File]::WriteAllText("$PWD\api\secrets\llm_api_key",      "<azure-ai-foundry-key>")
[IO.File]::WriteAllText("$PWD\api\secrets\wettenbank_token",  "<wettenbank-token>")   # = WETTENBANK_TOKEN uit env
[IO.File]::WriteAllText("$PWD\api\secrets\api_tokens",        "lokaal:<zelfgekozen-token>")
```

Genereer een willekeurig token: `[Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Maximum 256 }))`

### 2. `.env` aanmaken

Kopieer `.env.example` naar `.env` en vul in. Minimale Azure AI Foundry-config:

```
LLM_PROVIDER=azure_ai
LLM_MODEL=claude-sonnet-4-6
LLM_API_BASE=https://<resource-naam>.services.ai.azure.com   # geen /models achteraan
LLM_API_KEY_FILE=secrets/llm_api_key
WETTENBANK_TOKEN_FILE=secrets/wettenbank_token
WETSANALYSE_API_TOKENS_FILE=secrets/api_tokens
WETSANALYSE_ADMIN_TOKENS=admin:<zelfgekozen-admin-token>
LLM_CONFIG_SECRET=<fernet-key>   # nodig om API-keys via de admin-UI op te slaan
```

Genereer de Fernet-master-key met:
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

### 3. Server starten

```bash
cd api
uv sync --extra llm --extra dev
uv run --env-file .env uvicorn app.main:app --reload --port 3000
```

`uv run` laadt `.env` **niet** automatisch — de `--env-file .env` vlag is verplicht.
Swagger: `http://localhost:3000/docs` · health: `http://localhost:3000/health` · ready: `http://localhost:3000/ready`

### 4. Testen

```bash
uv run pytest -q               # unit-tests (fakes; geen netwerk)
# Fase 0-spike tegen echte MCP + Azure:
uv run --env-file .env --extra llm python scripts/spike_fase0.py BWBR0004770 9 1
```

**Geen vrije model-string vanuit de client**: kies een `model_profile` (benoemd, beheerd in de DB via
`/v1/admin/profiles` of het `/beheer`-scherm in de frontend); het feitelijk gebruikte model wordt per
ronde in de `provenance` van de `projects`-rij vastgelegd (audit). De env-`LLM_*`-waarden seeden
alleen het eerste default-profiel en blijven de fallback-key.

Lokaal heb je ook een **PostgreSQL** nodig (de jobstore). Snel:
`docker run -d -p 5432:5432 -e POSTGRES_USER=wetsanalyse -e POSTGRES_PASSWORD=wetsanalyse -e POSTGRES_DB=wetsanalyse postgres:16`
en zet `DATABASE_URL=postgresql+asyncpg://wetsanalyse:wetsanalyse@localhost:5432/wetsanalyse`. De
tabellen worden bij de start aangemaakt (`db.create_all` in de lifespan).

### Lokaal met Docker

Maak `api/docker-compose.override.yml` aan (gitignored) om de secrets-mount naar `./secrets` te
verwijzen in plaats van het productiepad. Voor lokaal draaien heb je naast `llm_api_key`,
`wettenbank_token` en `api_tokens` ook `database_url`, `postgres_user` en `postgres_password`
in `./secrets` nodig (zie de productie-stappen hieronder). Voor het LLM-beheer bovendien
`admin_tokens` en `llm_config_secret` — ontbreken die, dan boot de API gewoon, maar geeft
`/v1/admin/*` 401 (geen admin-tokens) en kun je geen API-key via de UI opslaan (geen master key):

```yaml
services:
  wetsanalyse-api:
    volumes:
      - ./secrets:/run/secrets:ro
  postgres:
    volumes:
      - ./secrets:/run/secrets:ro
```

Daarna: `docker compose up --build` vanuit `api/`. Er is geen `analyses/`-volume meer — de jobstore
is PostgreSQL.

## Deployment

**Postgres draait in productie als APARTE stack** (`deploy/postgres/`), niet meer in de api-stack —
zo recreate een api-image-redeploy de DB nooit (haalt de data-laag uit de Portainer-recreate-race).
De API verbindt cross-stack op `postgres:5432` met een **bounded connect-retry** bij cold start
(`main.py` → `_init_db_met_retry`, knoppen `WETSANALYSE_DB_CONNECT_RETRIES`/`_BACKOFF`). De
host-secrets (incl. `postgres_user`/`postgres_password`/`database_url`) zijn ongewijzigd en gedeeld via
`SECRETS_DIR`. Migratie + volume-behoud: zie `deploy/postgres/README.md`. (Lokaal mag je postgres nog
gewoon bundelen — zie *Lokaal draaien*.)

Docker-image + Portainer-stack achter NPM, net als de MCP (`docker-compose.yml`). De dienst is
**horizontaal schaalbaar**: state-transities lopen via een atomaire **state-CAS** (`store.claim`, één
`UPDATE … RETURNING`), dus `--workers >1` en `deploy.replicas >1` zijn veilig. Een geclaimde job draagt
een `owner` + `lease_until`; de owner houdt de lease vers (heartbeat) en schrijft fenced (alleen zolang
hij de job bezit), en een periodieke **reaper** ruimt jobs met een verlopen lease op (crashende worker →
job naar `fout`, herstelbaar via `retry`). Dezelfde reaper (én `reconcile_startup`) vangt ook
**verweesde `queued`-jobs** af: crasht het proces tussen de create-commit en de `run_initial`-claim,
dan gaat een `queued` zonder owner die ouder is dan de lease naar `fout` (retry/delete werken dan
weer; een `queued` project is bovendien direct door de gebruiker te verwijderen). Knoppen:
`WETSANALYSE_LEASE_S` (default 120) en
`WETSANALYSE_REAPER_INTERVAL_S` (default 60; 0 = uit). Kies de lease ruim langer dan de langste
realistische staptijd. De containers draaien **non-root** en **PostgreSQL draait met authenticatie**. Alle secrets (LLM-key, tokens, DB-credentials, connection string) staan
als bestanden op de host (`*_FILE`-patroon) — nooit als plain env var in de container of Portainer-UI.
Build vanaf de **projectroot**: `docker build -f api/Dockerfile -t wetsanalyse-api .` (de image heeft de
skill-`references/scripts` nodig). `POST /v1/projects` is async (202 + polling) — nooit synchroon achter
NPM's ~60s timeout.

### Secrets op de host (eenmalig, vóór de eerste stack-start)

De stack mount één host-map op `/run/secrets` in zowel de **api**- als de **postgres**-container. Het pad
komt uit de **GitHub Actions repo-variabele `SECRETS_DIR`** (Settings → Variables → Actions); de CI
geeft die door aan Portainer, dat `${SECRETS_DIR}` in de compose invult. **Staat de variabele leeg,
dan gebruikt de CI een default-pad en mount je de verkeerde map** → secrets onvindbaar (zie
Troubleshooting). Zet `SECRETS_DIR` dus exact op je host-pad, bijv. op een Synology NAS:
`/volume1/docker/wetsanalyse-api/secrets`.

Zes bestanden, aangemaakt op de **host zelf** (niet via een laptop-mount — die neemt de Unix-perms
vaak niet over):

```bash
SECRETS_DIR=/volume1/docker/wetsanalyse-api/secrets    # = de waarde van vars.SECRETS_DIR
sudo mkdir -p "$SECRETS_DIR"

echo -n "<llm-api-key>"      | sudo tee "$SECRETS_DIR/llm_api_key"      > /dev/null
echo -n "<wettenbank-token>" | sudo tee "$SECRETS_DIR/wettenbank_token"  > /dev/null
echo -n "id1:tok1,id2:tok2"  | sudo tee "$SECRETS_DIR/api_tokens"        > /dev/null

# Admin-laag (LLM-modelprofielen): aparte admin-tokens + Fernet-master-key voor key-versleuteling.
echo -n "admin:adm-tok"                                   | sudo tee "$SECRETS_DIR/admin_tokens"      > /dev/null
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" \
    | sudo tee "$SECRETS_DIR/llm_config_secret" > /dev/null

# PostgreSQL-auth: credentials + de connection string die de API gebruikt.
# Hex-wachtwoord = URL-veilig (geen +/=/ die je in de connection string moet escapen).
PG_USER=wetsanalyse
PG_PASS="$(openssl rand -hex 24)"
echo -n "$PG_USER" | sudo tee "$SECRETS_DIR/postgres_user" > /dev/null
echo -n "$PG_PASS" | sudo tee "$SECRETS_DIR/postgres_password" > /dev/null
echo -n "postgresql+asyncpg://$PG_USER:$PG_PASS@postgres:5432/wetsanalyse" \
    | sudo tee "$SECRETS_DIR/database_url" > /dev/null

# BELANGRIJK: de containers draaien non-root (postgres uid 999, api uid 10001). De bestanden zijn
# eigendom van je host-user, dus de container-users lezen ze alleen via de "other"-bit. Gebruik
# 644 (NIET 600 — dat geeft "Permission denied" in de container en postgres start niet).
sudo chmod 755 "$SECRETS_DIR"
sudo chmod 644 "$SECRETS_DIR"/*
```

**Postgres-volume.** De postgres-image initialiseert de user/db alleen bij een *lege* data-dir. Een
schone start is het simpelst: bestaat het `wetsanalyse-api_wetsanalyse_postgres`-volume al en wil je
verse credentials, verwijder het dan
(`docker rm -f wetsanalyse-postgres && docker volume rm wetsanalyse-api_wetsanalyse_postgres`). Wil je
*bestaande data* behouden, laat dan de credentials (en daarmee de `database_url`-secret) ongewijzigd.

Rotatie: pas het bestand aan en herstart (`docker restart wetsanalyse-api`); voor het Postgres-wachtwoord
ook de rol in Postgres bijwerken (`ALTER ROLE wetsanalyse WITH PASSWORD '…'`) én de `database_url`-secret.
CI stuurt geen geheime waarden naar Portainer — alleen niet-geheime config (`LLM_MODEL`, `LLM_PROVIDER`, e.d.)
en de niet-geheime `SECRETS_DIR`.

### Troubleshooting deploy

Symptoom → oorzaak:
- **API-log: kan niet verbinden met `localhost:5432` / `OperationalError`** — de `database_url`-secret werd
  niet gelezen (config viel terug op de default). Vrijwel altijd: `/run/secrets` wijst naar de verkeerde
  map → check `vars.SECRETS_DIR` en `docker inspect wetsanalyse-api --format '{{json .Mounts}}'`.
- **Postgres-log: `/run/secrets/postgres_password: Permission denied`, container `unhealthy`** —
  secret-bestanden niet leesbaar voor uid 999/10001 → `sudo chmod 644` op de host (zie boven).
- **Portainer stack-update HTTP 500** — meestal een container die niet start (een van bovenstaande);
  kijk in de containerlogs (`docker logs wetsanalyse-postgres` / `wetsanalyse-api`), niet alleen in de CI.

## Misbruik-/kostenbeheersing

Knoppen via env (0 = uit): `WETSANALYSE_RATE_LIMIT_MAX`/`_WINDOW` (per-client request-rate op de
muterende endpoints → 429), `WETSANALYSE_ADMIN_TEST_RATE_MAX`/`_WINDOW` (aparte, krappe limiet op
`POST /v1/admin/profiles/{name}/test` → 429; die doet een betaalde LLM-call achter alleen het
admin-token. De testfout is bovendien gesaniteerd: een vaste melding in de respons, de ruwe
provider-fout alleen in het server-log — dezelfde sanitisatie geldt voor `job.error.bericht`:
een rauwe provider-/interne fout landt als vaste melding, de details alleen in het server-log.
De in-process rate-limiter is begrensd (sweep + harde cap op het aantal sleutels, fail-closed)
zodat aanvaller-gekozen sleutels via de publieke login-route het geheugen niet vol pompen), `WETSANALYSE_MAX_ACTIVE_JOBS` (max gelijktijdig lopende analyses per
client → 429), `WETSANALYSE_LLM_TOKEN_BUDGET` (token-plafond per analyse → job naar `fout`,
`FoutKlasse.quota`), `WETSANALYSE_LLM_MAX_CONCURRENCY` (globaal plafond op gelijktijdige LLM-calls,
default 4 — de echte rem tegen provider-rate-limits), `WETSANALYSE_LLM_TIMEOUT_S` (harde wandklok-
timeout per LLM-call, **default 300**; 0 = uit — een hele act-2/act-3-ronde kan bij een traag
provider-model >2 min duren, vandaar ruimer dan de oude 120; veilig t.o.v. de lease omdat de
heartbeat die mid-call ververst), `WETSANALYSE_LLM_MAX_PROMPT_TOKENS` (harde cap op prompt-tokens
per call; 0 = auto-afleiden uit het model, onbekend model → geen limiet — bij overschrijding faalt
de call met een duidelijke `PromptTooLargeError` i.p.v. een rauwe 400; act-3 stuurt bewust de
volledige leden-tekst mee zodat definities dicht op de bron blijven — deze token-guard is de
bewaking van dat contextrisico),
`WETSANALYSE_MAX_VERWIJZING_FETCHES` (cap op het aantal
verwezen artikelen dat per analyse wordt opgehaald in de cross-referentie-fetch-lus, default 6;
0 = niet volgen), `WETSANALYSE_LLM_PROMPT_CACHING` (prompt caching aan/uit, **default 1/aan**;
de prompt-builders zetten de vaste references in het **system**-bericht en de LLM-laag markeert
dat blok als cachebaar (`cache_control: ephemeral`) — de references vormen per fase/stap een
byte-stabiele prefix, dus opeenvolgende bronnen én revisierondes lezen ze uit de cache i.p.v. ze
elke call vol te betalen. Verlaagt kosten/latency, niet het window zelf. Zet op 0 als de provider
`cache_control` niet ondersteunt → terug naar het oude gedrag, geen regressie. De cache-besparing
is zichtbaar via `cache_read_in`/`cache_write_in` in de `provenance` en in `/v1/admin/usage`). Een 429 wordt bovendien geretryed met respect
voor de `Retry-After`-header (`WETSANALYSE_TRANSIENT_MAX_RETRIES`/`_BACKOFF`/`_MAX_BACKOFF`). Let op
bij >1 replica: de **rate limit** én de **LLM-concurrency-rem** zijn in-process (per replica → de
effectieve grens schaalt mee met het aantal replica's); **max-active-jobs** en het token-budget zijn
DB-/`provenance`-gebaseerd en dus accuraat over replica's heen. Multi-tenant isolatie is afgedwongen:
elke analyse is client-gescopet (404 op andermans id).

## Roadmap (nog niet gebouwd)

MS Teams-client; wet-only resolutie (nu is `bwbId` verplicht); echte job-queue (werk-distributie:
nu draait een analyse op de replica die het request kreeg — horizontaal schalen geeft spreiding van
verschillende analyses, geen parallellisme binnen één analyse).

**Login (gebouwd).** De webapp zit achter een login met **userid** + wachtwoord (e-mail wordt
verplicht/uniek geregistreerd, maar is geen inlog-identiteit), rollen (`beheerder`/`analist`) en
optionele TOTP-2FA — zie `routers/auth.py` + `users.py`. De analyses zelf blijven
voorlopig **gedeeld** (alle ingelogde gebruikers delen de upstream API-client van de BFF); per-
gebruiker gescheiden werkruimtes (de gebruikersidentiteit doorvoeren tot in de project-scoping) en
externe IdP/OIDC blijven toekomstwerk.

**Cross-referenties (gebouwd).** Activiteit 2 is twee-fase: een lichte inventaris-stap
(`prompts.act2_inventaris_prompt`, geeft per verwijzing `functie` + `volgen`) gevolgd door een
begrensde deterministische fetch-lus (`orchestrator._volg_verwijzingen`, diepte 1, cap
`WETSANALYSE_MAX_VERWIJZING_FETCHES`, gefaalde fetch degradeert stil), waarna het LLM in act-2b
`betekenis`/`status` brongetrouw invult met de opgehaalde tekst. `wettenbank.parse_jci` stuurt de
fetch; de MCP-getagde verwijzingen (per lid) voeden de inventaris. Het rapport draagt een
`verwijzingen`-array; begrippen kunnen via `bron_verwijzing` op een definitie-verwijzing steunen.
Diepere navolging (verwezen artikelen vól door de JAS-werkstroom halen i.p.v. alleen de tekst
meenemen) blijft toekomstwerk.

De **webapp** is inmiddels gebouwd: zie `frontend/` (Next.js BFF) — analyses aanmaken, reviewen, en
de LLM-modelprofielen beheren via `/beheer`.
