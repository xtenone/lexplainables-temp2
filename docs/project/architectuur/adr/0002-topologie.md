# ADR-0002: Topologie

**Status:** geaccepteerd
**Datum:** 2026-08-26

## Context

Werkwijze-ADR-0002 stelt vast dát een applicatie uit meerdere, onafhankelijk deploybare services
bestaat, maar laat open hoeveel, hoe ze heten en hoe ze communiceren. Voor dit project is dat al
grotendeels gegeven: `wetsanalyse-ai`, waarvan dit de architectuur-refactor is, is zelf al een
multi-service-opzet (`api`, `frontend`, `graph-qa`, `tools/bwb-import`, GraphDB,
`tools/wetsanalyse-admin-mcp`) met aparte deploy-images per onderdeel. Dit ADR legt alleen vast
welk deel daarvan in déze repo zit en hoe `api` intern is heringedeeld — het verzint de topologie
niet opnieuw.

`api` bevatte vóór deze refactor zeven domeinen (identiteit_toegang, api_tokens, llm_profielen,
annotatie, gesprekken, berichten, feedback) door elkaar in verzamelbestanden: één 233-regelig
`db.py` met alle tabellen, één 489-regelig `routers/admin.py` met vijf domeinen se admin-CRUD.

## Beslissing

**Zes services in deze repo** (bijgewerkt 2026-08-26 — de eerste versie van dit ADR had er twee;
`graph-qa`, `deploy/graphdb`, `tools/bwb-import` en `tools/wetsanalyse-admin-mcp` zijn er sindsdien
bijgekomen, op expliciet verzoek):

1. **`api`** — kernbackend. Blijft één service (dezelfde afweging als in `wetsanalyse-ai`/
   `lexplainables`: de domeinen delen dezelfde auth en users-tabel; verder opsplitsen voegt
   cross-service-contractlast toe zonder een reëel schaalvoordeel). Intern vertical-sliced per
   domein (werkwijze-ADR-0001) — zie `docs/project/architectuur/stack-profiel.md` §Feature-eenheid.
2. **`frontend`** — hoofdwebapp (Next.js BFF). **Ongewijzigd overgenomen en blijft dat**: dit is
   een expliciete eis van de opdrachtgever voor deze refactor, geen architectuurkeuze van deze
   werkwijze. Praat met `api` én, voor de live chat, rechtstreeks met `graph-qa`.
3. **`graph-qa`** — de QA-/annotatie-agent ("Lex"). **1:1 overgenomen, bewust niet intern
   herstructureerd** — expliciet verzoek van de opdrachtgever, geen scope-beperking zoals bij
   `frontend` (hier gaat het om waar de tijd in gaat zitten, niet om een harde eis): een
   ~6200-regelige LangGraph-agent met een eigen, al goed gescheiden lagenindeling (`agent/`
   domein, `api/` HTTP, poorten/adapters voor DI) had weinig te winnen bij een geforceerde
   feature-map-vorm die niet bij een agent-architectuur past.
4. **`tools/bwb-import`** — ETL: BWB-wetteksten → GraphDB. **Grotendeels ongewijzigd
   overgenomen**: een lineaire pipeline (discovery → download → XSD-validatie → parsen →
   RDF-schrijven) heeft geen meerdere domeinen om vertical te slicen — de feature-map-vorm is
   hier niet van toepassing, niet overgeslagen.
5. **`deploy/graphdb`** — deployconfig voor de kennisgraaf zelf (third-party image, geen
   applicatiecode van dit project).
6. **`tools/wetsanalyse-admin-mcp`** — stdio-MCP die `api`'s `/v1/admin/*` ontsluit. Triviaal,
   1:1 overgenomen.

**Orkestratie:** er is geen aparte orkestratie-module meer in `api` — de vroegere
analyse-pijplijn (`projects`/`rondes`, act2/act3) is in `wetsanalyse-ai` zelf al verwijderd vóór
deze refactor begon; de agentische annotatie draait in `graph-qa`.

**Communicatie:** synchroon HTTP/SPARQL/MCP. Geen events — dat is ongewijzigd t.o.v.
`wetsanalyse-ai`.

## Consequenties

- `docs/project/architectuur/stack-profiel.md` §Topologie verwijst naar dit ADR.
- De winst zit in de interne herindeling van `api`, niet in het aantal services in deze repo —
  dat was ook al zo bij het zusterproject `lexplainables`.
- **`graph-qa` en `tools/bwb-import` volgen bewust niet dezelfde interne herindeling als `api`.**
  Dat is geen inconsistentie: de feature-map-architectuur (werkwijze-ADR-0001/0011) lost een
  specifiek probleem op — meerdere domeinen die door elkaar in verzamelbestanden zitten — en dat
  probleem had `api` (zeven domeinen, een 233-regelig `db.py`, een 489-regelig `routers/admin.py`)
  wél en `graph-qa`/`bwb-import` niet.
- **Bekende, niet-architecturale blokkade (geen onderdeel van dit ADR):** GraphDB draait hier
  zonder licentie — read/write op data geeft `500 No license was set` tot die er is. `graph-qa`
  heeft daarnaast geen echte LLM-key. Beide diensten booten en zijn live geverifieerd tot aan die
  grens (zie `stack-profiel.md` §Topologie en §Nog open).
