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

**In deze repo staan nu twee services:**

1. **`api`** — kernbackend. Blijft één service (dezelfde afweging als in `wetsanalyse-ai`/
   `lexplainables`: de domeinen delen dezelfde auth en users-tabel; verder opsplitsen voegt
   cross-service-contractlast toe zonder een reëel schaalvoordeel). Intern vertical-sliced per
   domein (werkwijze-ADR-0001) — zie `docs/project/architectuur/stack-profiel.md` §Feature-eenheid.
2. **`frontend`** — hoofdwebapp (Next.js BFF). **Ongewijzigd overgenomen en blijft dat**: dit is
   een expliciete eis van de opdrachtgever voor deze refactor, geen architectuurkeuze van deze
   werkwijze. Praat met `api` én, voor de live chat, rechtstreeks met `graph-qa`.

**Nog niet in deze repo, wel nodig voor de volledige functionaliteit:**

- **`graph-qa`** — de QA-/annotatie-agent ("Lex"). Zonder deze dienst werkt de werkplek-chat
  niet: login, beheer en instellingen wel.
- **GraphDB** (de kennisgraaf) + **`tools/bwb-import`** (ETL die 'm vult).
- **`tools/wetsanalyse-admin-mcp`** — admin-MCP, los van `api`'s eigen admin-oppervlak.

Deze vier bestaan al in `wetsanalyse-ai` zelf; ze overnemen naar deze repo is openstaand werk
(zie `stack-profiel.md` §Nog open), geen onderdeel van dit ADR.

**Orkestratie:** er is geen aparte orkestratie-module meer in `api` — de vroegere
analyse-pijplijn (`projects`/`rondes`, act2/act3) is in `wetsanalyse-ai` zelf al verwijderd vóór
deze refactor begon; de agentische annotatie draait in `graph-qa`.

**Communicatie:** synchroon HTTP. Geen events — dat is ongewijzigd t.o.v. `wetsanalyse-ai`.

## Consequenties

- `docs/project/architectuur/stack-profiel.md` §Topologie verwijst naar dit ADR.
- De winst zit in de interne herindeling van `api`, niet in het aantal services in deze repo —
  dat was ook al zo bij het zusterproject `lexplainables`.
- **Nadeel, bewust geaccepteerd:** zolang `graph-qa`/GraphDB/`bwb-import` niet in deze repo staan,
  is de werkplek-chat in deze repo een lege/foutmeldende schil. Dat is een bewuste, gefaseerde
  volgorde (eerst `api` correct herindelen, dan de rest overnemen), geen vergeten stap.
- **Nog niet besloten:** wanneer/hoe `graph-qa` + GraphDB + `bwb-import` naar deze repo
  overkomen, en of dat 1:1 dezelfde interne herindeling krijgt als `api` nu kreeg.
