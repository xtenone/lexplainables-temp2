# CLAUDE.md — lexplainables-temp2

Architectuur-refactor van `wetsanalyse-ai`: hetzelfde project, herstructureerd naar de
multi-service contract-first werkwijze. De methodologie, skills en achtergrond staan in dit
repo zelf onder [`docs/project/werkwijze/`](docs/project/werkwijze/CLAUDE.md) (geen
sibling-repo-dependency). **De werkwijze zelf hoeft tijdens deze refactor niet gevolgd te
worden** (geen story-review/PR-ceremonie) — dat geldt pas weer voor nieuwe features erna.

**Harde eis, niet-onderhandelbaar:** `frontend/` blijft byte-voor-byte gelijk aan
`wetsanalyse-ai/frontend`. Dat is geen architectuurkeuze van deze werkwijze maar een expliciete
eis van de opdrachtgever — raak die map niet aan tijdens deze refactor.

## Stand van zaken

- **`docs/project/architectuur/stack-profiel.md`** is ingevuld — zie daar voor de volledige
  architectuurkeuzes (topologie, database, migraties, contractgeneratie, auth, …), en
  `docs/project/architectuur/adr/` voor de onderbouwing (`0001` Postgres, `0002` topologie).
- **`api/`** is herstructureerd naar `app/shared/` + `app/features/<domein>/
  {models.py,store.py,router.py,tests/}` voor identiteit_toegang, api_tokens, llm_profielen,
  annotatie, gesprekken, berichten, feedback. Gedrag ongewijzigd t.o.v. `wetsanalyse-ai` — dit
  was een verplaatsing, geen herimplementatie. Alembic-migraties + contractgeneratie
  (`scripts/genereer-types.sh` → OpenAPI → `frontend/generated/types.ts`) zijn ingericht. Alle
  tests slagen; end-to-end geverifieerd tegen een lokale Postgres via de echte frontend.
- **`frontend/`** is 1:1 overgenomen van `wetsanalyse-ai` en blijft dat. Gebruikt de gegenereerde
  types nog niet — dat volgt pas als de frontend zelf expliciet aan de beurt is.
- **`tools/graph-qa/`** (de "Lex"-agent), **`tools/bwb-import/`** (ETL naar de kennisgraaf),
  **`deploy/graphdb/`** en **`tools/wetsanalyse-admin-mcp/`** zijn overgenomen — `graph-qa` en
  `wetsanalyse-admin-mcp` 1:1, `bwb-import` grotendeels ongewijzigd (een lineaire ETL-pipeline
  heeft geen feature-map nodig). Zie `docs/project/architectuur/adr/0002-topologie.md`.
  **Twee bekende, niet-architecturale blokkades:** GraphDB heeft hier geen licentie (read/write
  geeft `500 No license was set`; de pipeline is live geverifieerd tot aan die grens) en
  `graph-qa` heeft geen echte LLM-key (boot en degradeert netjes zonder).
- **CI** (GitHub Actions, `.github/workflows/`) draait per service: test + stijl-check voor elke
  dienst, plus `check-migraties` (Alembic upgrade+downgrade) en `check-generated-types`
  (contract-drift tussen `api/generated` en `frontend/generated`) voor `api/`+`frontend/`.
- **Nog open:** GraphDB-licentie, LLM-key, en het aansluiten van `frontend/generated/types.ts` op de
  werkelijke frontend-code (blijft bewust ongebruikt tot de frontend zelf expliciet aan de beurt is).

## Lokaal draaien

Zie `api/README.md`/`api/CLAUDE.md`, `frontend/README.md`, `tools/graph-qa/README.md`,
`tools/bwb-import/README.md` voor de operationele details per service. Kort: Postgres + GraphDB
lokaal via podman (geen Docker beschikbaar in de dev-sandbox waar dit project tot nu toe in
ontwikkeld is; `docker.io/library/postgres:16` resp. `docker.io/ontotext/graphdb:11.4.0`),
`cd api && uv run alembic upgrade head` vóór de eerste start van de API, dan per service zijn
eigen dev-server (`uvicorn`/`npm run dev`/`uv run uvicorn api.main:app`).
