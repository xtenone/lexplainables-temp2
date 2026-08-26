# graph-qa — Lex

> **De dienst heet `graph-qa`, de assistent heet Lex.** Naar de gebruiker stelt de agent zich voor als
> **Lex**, het hulpmiddel voor wetsanalyse; de map, het image (`ghcr.io/palmw01/graph-qa`), de stack en
> de env-vars houden hun technische naam. Zijn zelfbeschrijving staat in het IDENTITEIT-blok van
> `agent/prompts.py`, zijn toon in `docs/schrijfrichtlijn-lex.md`.

Een vraag-antwoorddienst voor **Nederlandse invorderings- en belastingwetgeving** die in een
**GraphDB-kennisgraaf** is opgeslagen. `graph-qa` beantwoordt een natuurlijke-taalvraag door die graaf
te bevragen en het antwoord **uitsluitend** te baseren op wat de graaf teruggeeft — met een
letterlijke vindplaats (regeling / artikel / lid) en een bronnenlijst die herleidbaar is tot de
daadwerkelijk uitgevoerde queries. Het is een Python/FastAPI-dienst; de agentlogica draait op een
LangGraph-toestandsmachine met een LLM (Anthropic via Azure AI Foundry).

## Wat de agent doet

De kern is **brongetrouwheid**: het model mag niet uit eigen kennis antwoorden. Voor elke inhoudelijke
vraag bevraagt de agent eerst de graaf via een **getypeerde toollaag**, en een aparte controlestap
verifieert achteraf dat elke citaat in het antwoord ook echt uit een tool-resultaat komt. Vragen die
niet over de wetgeving in de graaf gaan, worden beleefd afgewezen.

Eén opdracht doorloopt een LangGraph-graaf. Een **supervisor** kiest eerst welke worker hem
behandelt; een vraag die niet over wetgeving gaat wordt daar al afgewezen.

**De antwoord-worker** — voor vragen:

1. **Specialist (reason ↔ retrieve)** — de gekozen specialist (definitie/duiding/algemeen) redeneert
   en roept tools aan; de agent voert die uit tegen de graaf en voegt de resultaten toe aan een
   *tool-trace*. Dit herhaalt tot er geen tool-aanroep meer volgt (of tot een beurten-limiet).
2. **Verify (grounding)** — deterministische controle of de vindplaatsen én de citaten in het
   antwoord voorkomen in de tool-trace. Wat niet klopt wordt gemarkeerd; desgewenst volgt één
   corrigerende her-vraag.
3. **Finalize** — de bronnenlijst wordt uit de tool-trace opgebouwd en beperkt tot de in het antwoord
   aangehaalde regelingen; het antwoord, de bronnen en het grounding-oordeel worden uitgestuurd.

**De annotatie-worker** — voor een opdracht als *"annoteer artikel 36 lid 4 van de Invorderingswet
1990"*: ophalen → annoteren → **Critic** → de eenduidige correcties door code laten uitvoeren → een
eindbeoordeling → de elementen uitsturen. Elk voorstel is een letterlijk fragment met een JAS-klasse
en een aandacht-niveau (🟢🟡🔴); de jurist beoordeelt ze in de werkplek. Zie `CLAUDE.md` voor de
volledige keten en de regels die daarbij gelden.

### Decompositie (multi-hop, optioneel)

Met `ENABLE_DECOMPOSITION=1` splitst een aparte stap een samengestelde vraag eerst in geordende
**deelvragen**; elke deelvraag krijgt een eigen retrieval-loop (waarbij eerdere bevindingen latere
deelvragen voeden), en een synthese-stap stelt het eind-antwoord samen uit de bevindingen. Grounding en
bron-provenance werken ongewijzigd op het gesynthetiseerde antwoord tegen de over álle deelvragen
geaccumuleerde tool-trace. Een **enkelvoudige** vraag levert één deelvraag op en wordt **direct
gestreamd zonder synthese-stap** — zo betaalt een simpele lookup geen extra kosten; alleen écht
samengestelde vragen krijgen de volle multi-hop. Staat de toggle uit, dan draait de bovenstaande
enkele reason↔retrieve-lus.

### Specialisten (binnen de antwoord-worker)

De supervisor kiest per vraag één specialist; elk krijgt een eigen instructie én een **subset** van
de tools (`agent/specialists.py`):

| Specialist | Waarvoor | Kern-tools |
|---|---|---|
| `definitie` | Begrippen en definities herleiden en letterlijk citeren. | `resolve_begrip`, `get_artikel`/`get_lid`, `search_wetgeving`/`semantic_search` |
| `duiding` | Betekenis, structuur en samenhang van een bepaling; kruisverwijzingen volgen. | `get_context`, `follow_verwijzingen`, `referenced_by`, `get_artikel`/`get_lid` |
| `algemeen` | Overige juridische vragen. | Alle tools |

### De toollaag (retrieval)

Het model krijgt **geen** vrije SPARQL, maar een set van dertien getypeerde tools; alleen
`raw_sparql` is een afgeschermd laatste redmiddel:

- **Zoeken** — `search_wetgeving` (full-text/Lucene, exacte termen) en `semantic_search` (op betekenis,
  via een GraphDB-similarity-index; te combineren als hybride zoekstap).
- **Ophalen** — `get_artikel`, `get_lid`, `get_bepaling`.
- **Regelingen** — `list_regelingen`, `get_regeling_info` (soort, geldigheid, uitgevende organisatie).
- **Verwijzingen** — `follow_verwijzingen` (uitgaand), `referenced_by` (inkomend).
- **Context (GraphRAG)** — `get_context`: een bepaling mét haar bevattende delen, leden en
  verwijzingen in één query.
- **Begrippen** — `resolve_begrip` (SKOS-thesaurus).
- **Introspectie** — `graph_schema` (live omvang van de graaf).
- **Laatste redmiddel** — `raw_sparql` (read-only SELECT/CONSTRUCT/DESCRIBE).

### Brongetrouwheid, expliciet gemaakt

- **Bronnen uit de tool-trace, niet uit modeltekst.** De vindplaatsen (BWB-IRI's, jci-strings,
  BWB-id's) worden herkend in wat de graaf terugstuurde — een geparafraseerde of verzonnen citaat in
  de prozatekst wordt zo nooit als "bron" gepresenteerd.
- **Grounding-controle.** Deterministisch (geen extra LLM-call): een citaat geldt als onderbouwd zodra
  zijn BWB-id ergens in de opgehaalde tekst voorkomt; anders wordt het als *unsupported* gemeld.
- **Onderwerp-afbakening en injectie-weerbaarheid.** De agent behandelt tekst die uit de graaf komt
  als data, nooit als instructie, en houdt zich aan de scope ook als een bericht vraagt dat te negeren.

### Geheugen

Gesprekscontinuïteit loopt via een durable LangGraph-checkpointer (sleutel = het meegegeven
gespreks-/sessie-id). Naast de episodische berichten houdt de agent een set eerder geraadpleegde
bepalingen bij; die dient als aanknopingspunt voor verwijzingen als "dat artikel" — feiten worden
altijd opnieuw via de tools geverifieerd.

## API

**De werkplek loopt over de run-endpoints, niet over `/v1/chat`.** Een beurt duurt 60-90 seconden en
hoort niet aan één browserverbinding te hangen: de run draait als achtergrondtaak bij de agent en de
browser kijkt mee. Sluit je het tabblad, dan loopt het werk door.

| Endpoint | Doel |
|---|---|
| `GET /health` | Liveness (geen auth). |
| `POST /v1/runs` | Start een beurt; geeft `run_id`. **409 + het lopende run_id** als er al een run voor dit gesprek is. Body als bij `/v1/chat`, plus optioneel `doel` (dan slaat de keten het zoeken over) en `modus: "advies"`. |
| `GET /v1/runs/{id}/events?vanaf=<seq>` | **SSE**: eerst replay vanaf `vanaf`, dan live. Elk frame draagt zijn `seq`, zodat je na een onderbreking op het juiste punt aanhaakt. |
| `POST /v1/runs/{id}/cancel` | 202 — stoppen is een verzoek, geen feit: de lopende stap maakt zichzelf af. |
| `GET /v1/conversations/{id}/run` | De run waar je op kunt aanhaken, of `null`. |
| `DELETE /v1/conversations/{id}` | Wist het agent-geheugen van één gesprek (idempotent → 204) en stopt een lopende beurt. |
| `POST /v1/chat` | Eén beurt **aan de verbinding gekoppeld** (SSE; body `{question, conversation_id?}`). Zonder eigenaarscontrole, dus niet de weg voor de webapp — bedoeld voor scripts en handmatig testen. |
| `GET /v1/artikel` | Artikeltekst uit de kennisgraaf voor het documentpaneel van de werkplek: query `bwb_id`, `artikel`, optioneel `lid`. |

**De events** zijn hetzelfde over beide wegen: `status` · `reason` (denkproces) · `token`
(eindantwoord) · `sources` · `grounding` · `conversation_id` · `done` · `error`. Draait de
annotatie-worker, dan komen daar `doel` · `element` (per brongetrouw JAS-element, mét `aandacht`
🟢🟡🔴 + `critic`) · `ontbrekend` · `suggestie` · `kandidaten` · `run` · `opgeslagen` ·
`waarschuwing` bij. Over de run-events kan er ook een `gat` voorbijkomen: dan is er vluchtig verkeer
weggevallen bij het cappen van de log, en toont de client "…" in plaats van een verminkt antwoord.

**Authenticatie.** `QA_API_TOKEN` wordt timing-safe vergeleken. Legt de agent zijn beurten zelf vast
bij de wetsanalyse-API (`WETSANALYSE_API_URL` + `_TOKEN` gezet), dan is dat token **verplicht** en weigert de
dienst te starten zonder — het schrijfpad naar de api is niet aan één gebruiker gebonden. Verdere
beveiliging: CORS met credentials uitsluitend bij een expliciete origin-lijst, een rate-limit **per
gebruiker** (`X-User-Id`, met het IP als terugval), en een read-only-vangnet dat SPARQL-updates
weigert.

## Lokaal draaien

Vereist [`uv`](https://docs.astral.sh/uv/). Zet minimaal `GRAPHDB_TOKEN` en de Azure-Foundry-variabelen
(zie `.env.example`). **Zonder `GRAPHDB_TOKEN` weigert de dienst te starten** — er mag geen tokenloos
verkeer naar de graaf lopen.

```bash
cd tools/graph-qa
cp .env.example .env          # vul GRAPHDB_TOKEN + AZURE_FOUNDRY_* in
uv run graph-qa               # uvicorn op poort 8080

uv run --extra dev pytest -q                    # tests
.venv/bin/python eval/run_eval.py --offline     # eval-harnas (fakes, geen netwerk/kosten)
```

## Configuratie (env)

| Variabele | Betekenis |
|---|---|
| `GRAPHDB_TOKEN` *(verplicht)* | Bearer-token voor de GraphDB-MCP. Ook als `GRAPHDB_TOKEN_FILE` (bestandspad, voor container-secrets). |
| `GRAPHDB_MCP_URL` | MCP-endpoint van de graaf. |
| `GRAPHDB_REPOSITORY_ID` | Repository (default `inning`). |
| `SIMILARITY_INDEX` | Naam van de GraphDB-similarity-index voor `semantic_search`. Leeg → die tool degradeert naar `search_wetgeving`. Zie `docs/embeddings-runbook.md`. |
| `AZURE_FOUNDRY_API_KEY` *(verplicht)* | Azure-AI-Foundry-key (of `_FILE`). |
| `AZURE_FOUNDRY_BASE_URL` *(verplicht)* | Foundry-endpoint **met** `/anthropic`-suffix. |
| `LLM_MODEL` | Modelnaam (default `claude-sonnet-4-6`). Draagt de annoteerder, de Critic en de QA-specialisten — die hebben bewust géén eigen knop. |
| `LLM_MODEL_ROUTER` | Model voor de supervisor (kiest de worker; 300 tokens, respons wordt toch hard gesaneerd). Leeg = `LLM_MODEL`. |
| `LLM_MODEL_OPHAAL` | Model voor de ophaal-agent. Leeg = `LLM_MODEL`. Verlaag pas na meting met `eval/run_eval.py`: kiest hij de verkeerde bepaling, dan is alles daarna brongetrouw én verkeerd. |
| `QA_API_TOKEN` | API-/chat-secret (of `_FILE`); leeg = open. |
| `CORS_ORIGINS` | Kommagescheiden origins; `*` = open (alleen dev). |
| `CHECKPOINT_DB_PATH` | Pad voor de durable checkpointer; leeg = in-memory (geen continuïteit over herstarts). |
| `MAX_TURNS` | Max. reason↔retrieve-beurten per vraag. |
| `GROUNDING_CORRECT` | Eén corrigerende ronde bij een ongegrond antwoord (verzonnen vindplaats of een citaat dat niet letterlijk is). **Default aan**; `false` maakt de controle weer alleen een melding onder het antwoord. Kost alleen een extra call als er werkelijk iets mis is. |
| `ENABLE_DECOMPOSITION` | `1` = multi-hop decompositie aan (default uit). |
| `MAX_SUBQUESTIONS` | Cap op het aantal deelvragen (default 5). |
| `SUB_MAX_TURNS` | Max. reason↔retrieve-beurten per deelvraag (default 8). |
| `CRITIC_MAX_RONDES` | Correctie na de Critic: **0 = uit**, **> 0 = aan** (default 2). Telt géén rondes meer ondanks de naam — de keten ligt vast (`annoteer → critic → patch → [herzie] → [critic] → emit`). Uit = exact `annoteer → critic → emit`. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP-endpoint; leeg = alleen gestructureerde JSON-logs (nul overhead). |

## De graaf

De dienst leest **read-only** uit een GraphDB-repository (`inning`) via een MCP-server (Streamable
HTTP transport; tools `sparql_query` en `similarity_search`). De data betreft invorderings- en
belastingregelingen: regelingen, artikelen, leden, kruisverwijzingen, een SKOS-begrippenthesaurus en
organisatie-/geldigheidsmetadata, met stabiele BWB-IRI's en jci-vindplaatsen.

## Verder lezen

- **`CLAUDE.md`** — werkgids bij het aanpassen van de code (architectuur, invarianten, valkuilen).
- `deploy/README.md` — containerimage, secrets als bestanden, Portainer-stack en CI.
- `docs/embeddings-runbook.md` — de GraphDB-similarity-index achter `semantic_search`.
