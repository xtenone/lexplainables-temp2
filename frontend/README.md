# Wetsanalyse-frontend

Next.js (App Router) + TypeScript-frontend. De app **is de werkplek**: een chat-achtige werkruimte
tegen de graph-qa-agent (login/beheer lopen via de [Wetsanalyse-API](../api)). De home leidt door naar
`/workbench`.

**De werkplek** (`/workbench`, de *Lex-pagina*): één gespreksvenster met **twee
werkwijzen** — **vragen** aan **Lex** (de assistent voor wetsanalyse; brongetrouwe Q&A over de
kennisgraaf) en
**JAS-annotatie** (de agent stelt JAS-elementen voor → de jurist reviewt per element:
approve/edit/reject/comment). Die pagina praat live met de graph-qa-agent (SSE) en bewaart de
review-state via de API. De home (`/`) leidt hierheen door.

**Het instellingenvenster** (`/instellingen/*`) opent als dialoog over de werkplek heen en draagt
account (wachtwoord, 2FA) plus — voor beheerders — het beheer: de modelprofielen die de agent
aansturen (toevoegen/bewerken/verwijderen, default kiezen, verbinding testen), **gebruikers** en
**API-tokens**. Het beheer loopt via aparte `/api/admin/*`-routes met een **apart admin-token**
(zie hieronder). `/beheer` en `/account` blijven als redirect bestaan.

## Architectuur — BFF met server-side token

De browser praat **uitsluitend** met de eigen Next.js-origin (`/api/**`). Die Route Handlers
(de _backend-for-frontend_) proxyen server-side naar de echte API en injecteren het Bearer-token.
Het token komt dus **nooit** in de browser. Dit lost ook twee dingen op: CORS vervalt (same-origin)
en Server-Sent Events werken (de native `EventSource` kan geen `Authorization`-header sturen — de
BFF doet dat server-side en pipet de stream door).

```
Browser ──/api/**──► Next.js (BFF, injecteert token) ──/v1/**──► wetsanalyse-api:3000
```

## Vormgeving — Rijkshuisstijl (Belastingdienst)

De app volgt de **Rijkshuisstijl** in het **Belastingdienst-stijlvak**: lintblauw `#154273` +
hemelblauw `#007bc7` op een witte achtergrond, een gecentreerde logobalk met het officiële
Belastingdienst-logo (het lint op de horizontale middenas), en **Fira Sans/Mono** als vrij
alternatief voor Rijksoverheid Sans, met responsive typografie (100/90/80% op desktop/tablet/mobiel).

Alle design tokens staan centraal — CSS-variabelen in `app/globals.css` → Tailwind in
`tailwind.config.ts` — en de primitives in `components/ui/` (48px-knoppen/velden, platte cards,
`Vormelement`-signatuur). De **JAS-klassekleuren** (`lib/jas.ts`) zijn de exacte labelkleuren uit
de officiële JAS-tabel `docs/wetsanalyse/wa-table.png`.

> Kleur en typografie lopen via de tokens — geen losse hex-waarden in componenten. Het officiële
> logo-asset (`public/belastingdienst-logo.svg`) blijft ongewijzigd.

## Lokaal draaien

Vereist een draaiende API (zie [`../api/CLAUDE.md`](../api/CLAUDE.md)) — lokaal of het publieke
domein.

```bash
cd frontend
cp .env.example .env.local      # vul API_BASE_URL en API_TOKEN
npm install
npm run dev                     # http://localhost:3000
```

`.env.local`:

```
API_BASE_URL=http://localhost:3000      # of https://api.wetsanalyse.example
API_TOKEN=<alleen-de-tokenwaarde>       # het deel NA de ":" uit de API-tokenlijst
ADMIN_API_TOKEN=<alleen-de-tokenwaarde> # idem, maar uit de ADMIN-tokenlijst (voor /beheer)
AUTH_SECRET=<openssl rand -base64 32>   # ondertekent de login-sessiecookie (Auth.js)
```

> **Eerste keer inloggen.** De webapp zit volledig achter een login. Inloggen gaat met een
> **userid** (inlognaam) + wachtwoord; e-mail wordt bij het aanmaken verplicht/uniek geregistreerd
> maar is geen inlog-identiteit. Is de users-tabel van de API nog leeg, dan stuurt de app je naar
> `/setup` om eenmalig de eerste **beheerder** aan te maken (userid + e-mail + wachtwoord); daarna
> sluit die route. Verdere gebruikers (rol `analist` of `beheerder`) voeg je toe via `/beheer` →
> **Gebruikers** (ze krijgen een eenmalig tijdelijk wachtwoord en zetten zelf hun wachtwoord op
> `/account`). 2FA (TOTP) is optioneel en zet je zelf aan via `/account`. Voor 2FA moet
> `LLM_CONFIG_SECRET` op de **API** gezet zijn (de TOTP-secrets worden ermee versleuteld).

> Draait de lokale API óók op poort 3000? Start de frontend dan op een andere poort:
> `npm run dev -- -p 3001`.

## Scripts

| Commando            | Doel                                         |
| ------------------- | -------------------------------------------- |
| `npm run dev`       | Dev-server (hot reload)                       |
| `npm run build`     | Productiebuild (`output: 'standalone'`)       |
| `npm start`         | Productieserver (na build)                    |
| `npm run lint`      | ESLint                                        |
| `npm run typecheck` | `tsc --noEmit`                                |

## Omgevingsvariabelen

| Variabele        | Default                       | Beschrijving                                                |
| ---------------- | ----------------------------- | ---------------------------------------------------------- |
| `API_BASE_URL`         | `http://wetsanalyse-api:3000` | Server-side adres van de API (intern in productie).            |
| `API_TOKEN`            | —                             | Bearer-token (server-side). Komt nooit in de browser.          |
| `API_TOKEN_FILE`       | —                             | Pad naar secret-bestand met het token (heeft voorrang).        |
| `ADMIN_API_TOKEN`      | —                             | Admin-bearer voor `/beheer` → `/v1/admin/*` (server-side).     |
| `ADMIN_API_TOKEN_FILE` | —                             | Pad naar secret-bestand met het admin-token (heeft voorrang).  |
| `AUTH_SECRET`          | —                             | Ondertekent de Auth.js-sessiecookie/JWT. Verplicht voor login. |
| `AUTH_URL`             | —                             | Publieke origin (bv. `https://wetsanalyse.example`). **Verplicht achter een reverse proxy** — anders redirecten login/logout naar het interne `0.0.0.0:3000`. |
| `GRAPH_QA_URL`         | `http://graph-qa:8080`        | Server-side adres van de graph-qa-agent (werkplek). |
| `GRAPH_QA_TOKEN`       | —                             | Bearer voor graph-qa (alleen nodig als die achter een token staat). Server-side. |
| `GRAPH_QA_TOKEN_FILE`  | —                             | Pad naar secret-bestand met het graph-qa-token (heeft voorrang). |

De **werkplek** (`/workbench`) praat met de graph-qa-agent via `GRAPH_QA_URL` (server-side, default
intern `http://graph-qa:8080`) en optioneel `GRAPH_QA_TOKEN`/`GRAPH_QA_TOKEN_FILE`. De BFF-routes
`app/api/annotatie/run/**` (starten, meekijken via SSE, stoppen) en `app/api/annotatie/artikel`
(`GET /v1/artikel`) houden dat token server-side.

## Observability

De BFF is geïnstrumenteerd via `@vercel/otel` (`instrumentation.ts`): auto-tracing van route handlers
+ uitgaande `fetch` met traceparent-propagatie, gated op `OTEL_EXPORTER_OTLP_ENDPOINT` (leeg = uit).
`lib/logger.ts` is de server-only gestructureerde JSON-logger. Zie `CLAUDE.md` §Observability en de
projectbrede [`../docs/observability.md`](../docs/observability.md) (incl. de optionele Grafana-stack
in `deploy/observability/`, die frontend-stdout-logs via Alloy naar Loki shipt).

## Docker / deployment

Multi-stage `Dockerfile` (standalone, non-root) + `docker-compose.yml` voor de Portainer-stack
achter Nginx Proxy Manager, identiek aan de API-stijl. CI:
`.github/workflows/frontend-docker-publish.yml` (test → build → GHCR → Trivy). De workflow
publiceert alleen het image; de stack-update is een aparte stap.

De stack joint op `wetsanalyse_internal` (van `deploy/postgres/`) en `observability_default`, en
**publiceert een hostpoort** (`HOST_PORT`, default 8080): NPM draait op een andere host en deelt geen
docker-netwerk, dus proxyen op containernaam kan niet.

Eénmalig op de host (in `SECRETS_DIR`, gedeeld met de API-stack), alle mode 644:
`frontend_api_token` met een tokenwaarde uit de API-tokenlijst, `frontend_admin_token` met een
tokenwaarde uit de **admin**-tokenlijst (voor de beheertab), en `frontend_auth_secret` voor de
login-sessie (`openssl rand -base64 32`). De container-entrypoint laadt dat laatste bestand in
`AUTH_SECRET` (`AUTH_SECRET_FILE=/run/secrets/frontend_auth_secret`), zodat het — net als de andere
tokens — een bestand blijft en niet als plain env in Portainer staat. 2FA hergebruikt de
API-secret `llm_config_secret` (geen extra frontend-bestand). Zet daarnaast de stack-env
**`AUTH_URL`** op de publieke origin (bv. `https://wetsanalyse.example`) — verplicht achter NPM,
anders redirecten login/logout naar het interne `0.0.0.0:3000`. In NPM een Proxy Host
`wetsanalyse.example` → `<docker-host-ip>:${HOST_PORT}`, met **proxy buffering uit** voor SSE (zie de
commentaarregels in `docker-compose.yml`).

> **Toegang.** De hele webapp zit achter een login met **userid + wachtwoord** (Auth.js);
> niet-ingelogde bezoekers landen op `/login`. De beheertabs (LLM-beheer + gebruikersbeheer) zijn
> bovendien rol-afgeschermd tot **beheerders**. Een losse NPM Access List is dus niet meer nodig;
> de eerste beheerder maak je eenmalig via `/setup`.

## Types up-to-date houden (optioneel)

`lib/types.ts` is met de hand afgeleid van `api/app/annotatie_contracts.py` (+ `gesprek_contracts.py`)
en is de bron-van-waarheid. Wil
je tegen het live OpenAPI-schema controleren:

```bash
npx openapi-typescript http://localhost:3000/openapi.json -o lib/openapi.d.ts
```

Vergelijk dat met `lib/types.ts` bij contractwijzigingen.
