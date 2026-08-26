# lexplainables-temp2

Architectuur-refactor van [`wetsanalyse-ai`](https://github.com/jaas0000/wetsanalyse-ai): hetzelfde
agent-platform voor **Wetsanalyse** (het gestructureerd, brongetrouw en traceerbaar duiden van
Nederlandse wet- en regelgeving volgens de methode Wetsanalyse en het Juridisch Analyseschema, JAS),
herstructureerd naar de multi-service, contract-first **werkwijze-v2**-architectuur. Zie
[`CLAUDE.md`](CLAUDE.md) voor de volledige uitleg van wat er wel/niet veranderd is, en
[`docs/project/architectuur/stack-profiel.md`](docs/project/architectuur/stack-profiel.md) +
[`docs/project/architectuur/adr/`](docs/project/architectuur/adr/) voor de architectuurkeuzes en hun
onderbouwing.

**Harde eis, niet-onderhandelbaar:** `frontend/` blijft byte-voor-byte gelijk aan
`wetsanalyse-ai/frontend`. Dat is geen keuze van deze werkwijze maar een expliciete eis van de
opdrachtgever.

## Onderdelen

| Onderdeel | Map | Wat het doet |
|-----------|-----|--------------|
| **wetsanalyse-API** | `api/` | FastAPI-backend voor de werkplek — JAS-annotatie, chatgeschiedenis, login/gebruikersbeheer, LLM-modelprofielen, berichten, feedback. Herstructureerd naar `app/shared/` + `app/features/<domein>/{models.py,store.py,router.py,tests/}`; schema komt uitsluitend van Alembic. |
| **frontend + werkplek** | `frontend/` | Next.js-webapp (BFF) met de werkplek (`/workbench`). 1:1 overgenomen van `wetsanalyse-ai`, ongewijzigd. |
| **graph-qa — Lex** | `tools/graph-qa/` | De QA/annotatie-agent (LangGraph): beantwoordt vragen over wetgeving en annoteert bepalingen via de BWB-kennisgraaf (GraphDB via MCP). 1:1 overgenomen — geen feature-map-restructurering, zie ADR-0002. |
| **BWB-importer** | `tools/bwb-import/` | ETL die wettekst bij overheid.nl ophaalt, valideert en als RDF naar GraphDB schrijft. Lineaire pipeline, grotendeels ongewijzigd. |
| **admin-MCP** | `tools/wetsanalyse-admin-mcp/` | MCP-server die de admin-API (`/v1/admin/*`) als agent-tools ontsluit. 1:1 overgenomen. |
| **de kennisgraaf** | `deploy/graphdb/` | GraphDB-deployconfig. |
| **docs** | `docs/` | Methodische onderbouwing (JAS, RegelSpraak) + `docs/project/` (werkwijze, architectuurdocumentatie/ADR's van déze refactor). |

## Stand van zaken

- `api/` is herstructureerd naar de feature-map-architectuur; gedrag ongewijzigd — een verplaatsing,
  geen herimplementatie. Alembic-migraties en contractgeneratie (OpenAPI → TypeScript) zijn ingericht.
- `frontend/` blijft 1:1 en gebruikt de gegenereerde types nog niet.
- `tools/graph-qa/`, `tools/bwb-import/`, `deploy/graphdb/` en `tools/wetsanalyse-admin-mcp/` zijn
  overgenomen. Twee bekende, niet-architecturale blokkades: GraphDB heeft hier geen licentie
  (read/write geeft `500 No license was set`; de pipeline is live geverifieerd tot aan die grens) en
  graph-qa heeft geen echte LLM-key (boot en degradeert netjes zonder).
- CI (GitHub Actions) draait per service: test + `check-python-style`/`check-ts-style` voor elke
  service, plus `check-migraties` (Alembic upgrade+downgrade) en `check-generated-types`
  (contract-drift) voor `api/`+`frontend/`. Zie `.github/workflows/`.

## Lokaal draaien

Zie `api/README.md`/`api/CLAUDE.md`, `frontend/README.md`, `tools/graph-qa/README.md`,
`tools/bwb-import/README.md` voor de operationele details per service. Kort: Postgres + GraphDB
lokaal via **podman** (`docker.io/library/postgres:16` resp. `docker.io/ontotext/graphdb:11.4.0`),
`cd api && uv run alembic upgrade head` vóór de eerste start van de API, dan per service zijn eigen
dev-server (`uvicorn`/`npm run dev`/`uv run uvicorn api.main:app`).

## Databron & licentie

De wettekst komt van de publieke diensten van `overheid.nl` (SRU + BWB-repository); geen API-key
nodig, data is CC-0. GraphDB vereist een Ontotext-licentie (community of commercieel) voor elke
lees/schrijf-operatie op de repository — repository-aanmaak zelf werkt ook zonder.
