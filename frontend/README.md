# Wetsanalyse-frontend

Next.js (App Router) + TypeScript-frontend voor de [Wetsanalyse-API](../api). Ontsluit de hele
JAS-workflow in de browser: analyse aanmaken, live voortgang, de human-in-the-loop review-lus en
het eindrapport — inclusief de **cross-referenties** (een Verwijzingen-sectie in het rapport, per
functie met status en `wetten.overheid.nl`-links, en per-verwijzing scope-feedback in de
activiteit-2 review). Bij het activiteit-2-checkpoint kan de analist ook **"Akkoord — afronden
zonder act. 3"** kiezen (`scope: "act2"`): de analyse gaat direct naar het rapport zonder
begrippen; op zo'n rapport verschijnt later de knop **"Activiteit 3 uitvoeren"** om act 3 alsnog
te draaien.

Op een afgeronde analyse kun je met **"Naar RegelSpraak"** de formaliseringsfase starten: dezelfde
twee-checkpoint review-lus (GegevensSpraak-objectmodel en RegelSpraak-regels), waarna een eigen
**RegelSpraak-weergave** het model toont (met herkomst per declaratie/regel) en een `.rs`/`.md`-download
biedt.

Daarnaast is er **de werkplek** (`/workbench`, de *Assistent-pagina*): één gespreksvenster met **twee
werkwijzen** — **vragen** aan de Juridische Assistent (brongetrouwe Q&A over de kennisgraaf) en
**JAS-annotatie** (de agent stelt JAS-elementen voor → de jurist reviewt per element:
approve/edit/reject/comment). Die pagina praat live met de graph-qa-agent (SSE) en bewaart de
review-state via de API.

Het geaggregeerde live-overzicht van álle analyses (per analyse de engine-stap tot op
**functieniveau**, met verstreken tijd, token-verbruik en foutstatus) is **verhuisd naar Grafana**
— het dashboard *"Wetsanalyse — systeemtopologie"* (`deploy/observability/`), gevoed door een
read-only view op de jobstore. De aggregate-SSE-route (`/api/projects/events`) blijft bestaan en
houdt de **home-projectenlijst** live.

De home-projectenlijst heeft een client-side **zoek-/filter-/sorteerbalk** (status, vrije
tekst op naam/BWB-id/artikel, wet) met **paginering**, bovenop de live SSE-lijst.

Daarnaast een **`/beheer`-scherm** voor het LLM-beheer: de modelprofielen die de analyses aansturen
(toevoegen/bewerken/verwijderen, default kiezen, verbinding testen), een **wet-catalogus** (BWB-id +
naam, met "Naam ophalen" via de MCP) en een overzicht van het token-verbruik. Bij **Nieuwe analyse**
kies je zowel het modelprofiel als de wet uit een dropdown die live wordt opgehaald, zodat
wijzigingen in de draaiende app direct meekomen; na de wet-keuze wordt **artikel** een combobox
met autocomplete op de echte wetsstructuur en **lid** een keuzelijst met de echte leden (plus een
bevestigingsregel met opschrift en tekstsnippet). De dropdowns zijn een gemak: is de catalogus
leeg of faalt de structuur-lookup, dan val je terug op vrije invoer. Optioneel plak of upload je
een **bestaande begrippenlijst** (JSON, CSV met kopregel, of `naam; definitie`-regels) als
suggestieve invoer voor activiteit 3 — de analyse registreert dan per begrip de herkomst
(hergebruikt/aangepast/nieuw). De JSON-vorm (alleen `naam` verplicht; een kale array mag ook):

```json
{
  "begrippen": [
    {
      "naam": "belastingplichtige",
      "synoniemen": ["plichtige"],
      "definitie": "degene die op grond van de wet gehouden is aangifte te doen",
      "klasse": "Rechtssubject",
      "bron": "Begrippenkader Heffing, versie 2025"
    },
    { "naam": "bijdrage-inkomen" }
  ]
}
```

Het beheer loopt via aparte `/api/admin/*`-routes met een
**apart admin-token** (zie hieronder).

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
de officiële JAS-tabel `docs/wa-table.png`; de job-state-kleuren staan in `lib/states.ts`.

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
API_BASE_URL=http://localhost:3000      # of https://wetsanalyse-api.ipalm.nl
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
| `AUTH_URL`             | —                             | Publieke origin (bv. `https://wetsanalyse.ipalm.nl`). **Verplicht achter een reverse proxy** — anders redirecten login/logout naar het interne `0.0.0.0:3000`. |
| `GRAPH_QA_URL`         | `http://graph-qa:8080`        | Server-side adres van de graph-qa-agent (werkplek). |
| `GRAPH_QA_TOKEN`       | —                             | Bearer voor graph-qa (alleen nodig als die achter een token staat). Server-side. |
| `GRAPH_QA_TOKEN_FILE`  | —                             | Pad naar secret-bestand met het graph-qa-token (heeft voorrang). |

De **werkplek** (`/workbench`) praat met de graph-qa-agent via `GRAPH_QA_URL` (server-side, default
intern `http://graph-qa:8080`) en optioneel `GRAPH_QA_TOKEN`/`GRAPH_QA_TOKEN_FILE`. De BFF-routes
`app/api/annotatie/agent` (SSE naar `POST /v1/chat`) en `app/api/annotatie/artikel` (`GET /v1/artikel`)
houden dat token server-side.

## Observability

De BFF is geïnstrumenteerd via `@vercel/otel` (`instrumentation.ts`): auto-tracing van route handlers
+ uitgaande `fetch` met traceparent-propagatie, gated op `OTEL_EXPORTER_OTLP_ENDPOINT` (leeg = uit).
`lib/logger.ts` is de server-only gestructureerde JSON-logger. Zie `CLAUDE.md` §Observability en de
projectbrede [`../docs/observability.md`](../docs/observability.md) (incl. de optionele Grafana-stack
in `deploy/observability/`, die frontend-stdout-logs via Alloy naar Loki shipt).

## Docker / deployment

Multi-stage `Dockerfile` (standalone, non-root) + `docker-compose.yml` voor de Portainer-stack
achter Nginx Proxy Manager, identiek aan de API/MCP-stijl. CI:
`.github/workflows/frontend-docker-publish.yml` (test → build → GHCR → Trivy → Portainer-redeploy).

Eénmalig op de host (in `SECRETS_DIR`, gedeeld met de API-stack), alle mode 644:
`frontend_api_token` met een tokenwaarde uit de API-tokenlijst, `frontend_admin_token` met een
tokenwaarde uit de **admin**-tokenlijst (voor `/beheer`), en `frontend_auth_secret` voor de
login-sessie (`openssl rand -base64 32`). De container-entrypoint laadt dat laatste bestand in
`AUTH_SECRET` (`AUTH_SECRET_FILE=/run/secrets/frontend_auth_secret`), zodat het — net als de andere
tokens — een bestand blijft en niet als plain env in Portainer staat. 2FA hergebruikt de
API-secret `llm_config_secret` (geen extra frontend-bestand). Zet daarnaast de stack-env
**`AUTH_URL`** op de publieke origin (bv. `https://wetsanalyse.ipalm.nl`) — verplicht achter NPM,
anders redirecten login/logout naar het interne `0.0.0.0:3000`. In NPM een Proxy Host
`wetsanalyse.ipalm.nl` → `wetsanalyse-frontend:3000`, met **proxy buffering uit** voor SSE (zie de
commentaarregels in `docker-compose.yml`).

> **Toegang.** De hele webapp zit achter een login met **userid + wachtwoord** (Auth.js);
> niet-ingelogde bezoekers landen op `/login`. `/beheer` (LLM-beheer + gebruikersbeheer) is
> bovendien rol-afgeschermd tot **beheerders**. Een losse NPM Access List is dus niet meer nodig;
> de eerste beheerder maak je eenmalig via `/setup`.

## Types up-to-date houden (optioneel)

`lib/types.ts` is met de hand afgeleid van `api/app/contracts.py` en is de bron-van-waarheid. Wil
je tegen het live OpenAPI-schema controleren:

```bash
npx openapi-typescript http://localhost:3000/openapi.json -o lib/openapi.d.ts
```

Vergelijk dat met `lib/types.ts` bij contractwijzigingen.
