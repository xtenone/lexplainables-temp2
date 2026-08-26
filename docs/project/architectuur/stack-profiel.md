# Stack-profiel — lexplainables-temp2 (wetsanalyse-refactor)

Wat dit project concreet gekozen heeft op de punten die de skills anders zouden aannemen (zie
werkwijze-ADR-0004). Dit project is een refactor van `wetsanalyse-ai` naar deze architectuur —
niet een herimplementatie: bestaand gedrag blijft, alleen de codestructuur volgt vanaf hier de
werkwijze. Waar zinvol is het patroon geport uit het zusterproject `lexplainables`, dat dezelfde
architectuur al eerder op een vergelijkbare domeinverzameling toepaste.

**Expliciete beperking van scope (bewust, geen open punt):** de frontend (`frontend/`) blijft
byte-voor-byte gelijk aan `wetsanalyse-ai/frontend` — dat is een harde eis van de opdrachtgever,
niet iets wat deze werkwijze oplegt. Alleen de backend (`api/`) volgt vanaf nu de architectuur.

## Topologie

Op dit moment twee services in deze repo:

| Service | Map | Verantwoordelijk voor | Praat met |
|---|---|---|---|
| `api` | `api/` | Login/gebruikersbeheer, LLM-modelprofielen, genereerbare API-tokens, het JAS-annotatiedomein van de werkplek, chatgeschiedenis (gesprekken), berichten (release notes), gebruikersfeedback | eigen database (PostgreSQL) |
| `frontend` | `frontend/` | Hoofdwebapp (BFF) — **ongewijzigd overgenomen van `wetsanalyse-ai`, blijft dat** | `api`, en rechtstreeks `graph-qa` (SSE, buiten `api` om — zie hieronder) |

**Nog niet in deze repo** (bestaan wel in `wetsanalyse-ai` zelf, en zijn nodig voor de
chat/annotatie-functie om echt iets te doen — dit is openstaand werk, geen architectuurkeuze):
`graph-qa` (de "Lex"-QA-/annotatie-agent), de GraphDB-kennisgraaf, `tools/bwb-import` (ETL naar
die graaf) en `tools/wetsanalyse-admin-mcp`. Zolang die ontbreken werkt login/beheer/instellingen
volledig, maar levert de werkplek-chat zelf niets op.

Communicatie: synchroon HTTP. Geen events.

## De ene bron

Per werkwijze-ADR-0011: een SQLAlchemy Core `Table` in `models.py` van de eigenaar-feature, plus
de Pydantic-modellen — in `models.py` zelf voor kleine domeinen, of in een apart `contracts.py`
wanneer dat overzichtelijker is bij een groter domein (`annotatie`, `gesprekken`). Mapping tussen
Table-rij en Pydantic-model is een expliciete, met de hand geschreven functie in `store.py`.

**Afwijking t.o.v. lexplainables, bewust:** één gedeelde `MetaData`-instantie in
`api/app/shared/db.py` (`shared.db.metadata`) i.p.v. een eigen `MetaData()` per feature. Elke
feature registreert zijn `Table`(s) daarop. Alembic accepteert een los `MetaData`-object voor
`target_metadata` net zo goed als een lijst — dit is simpeler voor de omvang van dit project, en
elke feature blijft evengoed "de ene bron" voor zijn eigen tabellen (het eigenaarschap zit op
bestandsniveau, niet op het aantal `MetaData`-instanties).

## Contractgeneratie

Ja. `api/scripts/genereer-types.sh` schrijft het OpenAPI-schema van de FastAPI-app naar
`api/generated/openapi.json`. `frontend/scripts/genereer-types.sh` genereert daaruit
`frontend/generated/types.ts` via `openapi-typescript` (werkwijze-ADR-0017: relatief pad, zolang
beide services in dezelfde monorepo staan).

**Nog niet gekoppeld aan de frontend-code**: de frontend blijft voorlopig zijn eigen,
met-de-hand-bijgehouden `frontend/lib/types.ts` gebruiken (ongewijzigd overgenomen van
wetsanalyse-ai). `frontend/generated/types.ts` bestaat vanaf nu wel en is up-to-date te houden
door het script opnieuw te draaien, maar niets importeert het nog — dat gebeurt pas zodra de
frontend zelf wordt aangepast (buiten scope van deze refactor).

## Feature-eenheid

`api/app/features/<domein>/`: `models.py` (Table(s) + Pydantic, of alleen Table(s) als een apart
`contracts.py` bestaat), optioneel `contracts.py`, `store.py` (persistentie- en servicelaag),
`router.py` (FastAPI-routes — publiek én, waar van toepassing, een eigen `admin_router` achter
`require_admin`), `tests/`.

Zeven domeinen: `identiteit_toegang`, `api_tokens`, `llm_profielen`, `annotatie`, `gesprekken`,
`berichten`, `feedback`.

**Vereenvoudiging t.o.v. het volledige werkwijze-ADR-0007-patroon, bewust en gemeld:** `store.py`
is nog module-functies, geen Protocol + klasse-implementatie. De ontkoppeling
(router → store-functies, geen rechtstreekse SQL in de router) is er wel; het formele
Protocol-contract is een mogelijke vervolgstap, geen blokkade voor nu.

## Dunne verzamelaars

`api/app/shared/`: `config.py`, `db.py` (alleen engine-beheer + gedeelde `metadata`, geen
tabellen), `auth.py` (bearer-verificatie), `secrets_crypto.py`, `observability.py`,
`ratelimit.py`. Bevat bewust geen domeinkennis — `architectuur-audit` bewaakt dat dit zo blijft.

## Database

**PostgreSQL — enige database, ook in tests** — zie [ADR-0001](adr/0001-postgresql-enige-database.md).
Driver: `asyncpg` (runtime), `psycopg2-binary` (Alembic sync-migraties). Lokaal via podman (zie
[[feedback-podman-not-docker]] in de projectmemory — geen Docker beschikbaar in de dev-sandbox).

## Migraties

Alembic (werkwijze-ADR-0005): `api/alembic/`, één historie voor de `api`-service.
`target_metadata` in `alembic/env.py` is `shared.db.metadata` (zie §De ene bron hierboven). Geen
`create_all()`/`reconcile_schema()` meer in de productie-opstartpad (`main.py`-lifespan) — schema
komt uitsluitend via `alembic upgrade head`, vóór het starten van de server. `create_all()` blijft
wél bestaan in `shared/db.py` als test-utility (unit-tests draaien 'm rechtstreeks tegen een
verse Postgres-testdatabase, buiten Alembic om — dat is geen productiepad).

## Auth

Ongewijzigd overgenomen gedrag van `wetsanalyse-ai`, nu in `api/app/features/identiteit_toegang/`
+ `shared/auth.py`: Auth.js in de frontend voor de browsersessie, de API blijft identiteitsbron.
Twee aparte bearer-lagen — client-tokens (`require_client`) en losstaande admin-tokens
(`require_admin`, env + genereerbare DB-tokens) — plus een vertrouwde `X-User-Id`-header voor
per-gebruiker scoping (`annotatie`, `gesprekken`). Rollen `beheerder`/`analist`, optionele
TOTP-2FA. Dit wijkt af van lexplainables' eigen (eenvoudigere) auth-model — hier is bewust het
bestaande, rijkere wetsanalyse-ai-gedrag behouden, niet vervangen.

## LLM-toegangslaag

`api/app/features/llm_profielen/llm/`: `LLMClient`-protocol + LiteLLM-implementatie + een
proces-globale concurrency-throttle. Ongewijzigd overgenomen gedrag — de enige LLM-call in `api`
is de admin-verbindingstest; de daadwerkelijke chat/annotatie-LLM-aanroepen horen bij `graph-qa`
(nog niet in deze repo, zie §Topologie).

## Observability

`api/app/shared/observability.py`: gestructureerde JSON-logging altijd aan, OpenTelemetry
(traces/metrics/logs) gated op `OTEL_EXPORTER_OTLP_ENDPOINT` — leeg = no-op.

## Rate limiting

`api/app/shared/ratelimit.py`: in-process, per client-ID, ongewijzigd overgenomen gedrag.

## Frontend(s)

Eén: `frontend/`, ongewijzigd overgenomen van `wetsanalyse-ai` en blijft dat totdat de frontend
zelf expliciet aan de beurt is (buiten scope van deze refactor). Praat met `api` via zijn eigen
BFF-routes (`app/api/**`) en met `graph-qa` rechtstreeks voor de live chat-SSE.

## Codestandaard

`ruff` voor `api` (nog niet in CI gewired — open punt). `frontend` behoudt zijn eigen, ongewijzigde
`eslint`/`prettier`-config van `wetsanalyse-ai`.

## Nog open (bewust niet in deze stap)

- CI (`check-migraties`, `check-generated-types`, `check-python-style`, …) — nog geen workflows.
- `graph-qa` + GraphDB + `tools/bwb-import` — de daadwerkelijke chat/annotatie-functionaliteit.
- Frontend aanpassen om `frontend/generated/types.ts` daadwerkelijk te gebruiken.
- Deploy-configuratie (Dockerfile/compose) aanpassen aan de nieuwe structuur — het huidige
  `api/Dockerfile` is bijgewerkt om `alembic upgrade head` vóór het opstarten te draaien, maar
  deploy-targets/secrets-provisioning zijn verder ongewijzigd overgenomen.
