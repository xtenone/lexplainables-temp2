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
  was een verplaatsing, geen herimplementatie. Alle tests slagen; end-to-end geverifieerd tegen
  een lokale Postgres via de echte frontend.
- **Alembic-migraties** en **contractgeneratie** (`scripts/genereer-types.sh` → OpenAPI →
  `frontend/generated/types.ts`) zijn ingericht — zie stack-profiel.md §Migraties/
  §Contractgeneratie. De frontend gebruikt de gegenereerde types nog niet (zie de harde eis
  hierboven); dat volgt pas als de frontend zelf aan de beurt is.
- **`frontend/`** is 1:1 overgenomen van `wetsanalyse-ai` en blijft dat.
- **Nog niet in deze repo:** `graph-qa` (de "Lex"-agent), GraphDB, `tools/bwb-import`,
  `tools/wetsanalyse-admin-mcp`. Zonder deze werkt login/beheer/instellingen volledig, maar de
  werkplek-chat zelf niet — zie `docs/project/architectuur/adr/0002-topologie.md`.
- **Nog open:** CI (`check-migraties`, `check-python-style`, …) bestaat nog niet.

## Lokaal draaien

Zie `api/README.md`/`api/CLAUDE.md` en `frontend/README.md` voor de operationele details per
service. Kort: PostgreSQL lokaal via podman (geen Docker beschikbaar in de dev-sandbox waar dit
project tot nu toe in ontwikkeld is), `cd api && uv run alembic upgrade head` vóór de eerste
start, dan `uv run uvicorn app.main:app --port 3000` en `cd frontend && npm run dev`.
