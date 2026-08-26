# Runbook — semantische (vector) retrieval voor de `inning`-graaf

Doel: naast de bestaande Lucene-FTS (`bwb_tekst`) **semantisch zoeken** mogelijk maken,
zodat de agent bepalingen vindt op *betekenis* (andere woorden dan de wettekst) i.p.v. alleen
op exacte termen.

> ✅ **STATUS (juli 2026): route A is LIVE.** Er draait een native GraphDB text-similarity-index
> `bwb_similarity` op `inning`; `semantic_search` gebruikt 'm via de MCP-tool `similarity_search`
> en is geactiveerd met `SIMILARITY_INDEX=bwb_similarity`. Live geverifieerd (omschrijvende vragen +
> eval-paraphrase-cases). Route C (Azure-embeddings) blijft de kwaliteits-upgrade wanneer er een
> embeddings-deployment is. De exact gebruikte index-config staat onder *Route A — uitgevoerd*.

## Uitgangssituatie (geverifieerd, juli 2026)

- **GraphDB 11.4.0 Free**, repo `inning` (RUNNING, read+write), connectors-engine 16.7.0.
- Retrieval-indexen nu: **alleen** de Lucene-connector `bwb_tekst`. Geen similarity-index,
  geen autocomplete-index, geen Elasticsearch/OpenSearch/Solr/Kafka/ChatGPT-Retrieval-instances.
- De GraphDB-`similarity_search`-MCP-tool vraagt om een `similarityIndex` → de **Similarity-plugin
  is aanwezig**, er is alleen nog geen index.

> ⚠️ **Doe dit eerst:** de GraphDB-REST op `https://graphdb.example` staat **open (geen auth) en
> writable**. Zet 'm achter authenticatie (GraphDB Security aanzetten + NPM-basic-auth of een
> service-account), anders is elke read-only-garantie in de MCP-client omzeilbaar. Zonder dit is
> een vector-index net zo goed publiek muteerbaar.

## Twee routes

### Route A — GraphDB Similarity-plugin (native, geen externe API) — snelste
GraphDB traint zélf semantische vectoren over de literals (`bwb:tekst`). Geen embedding-endpoint,
geen kosten. Kwaliteit is *modest* (corpus-getraind, geen modern taalmodel), maar het werkt direct
en de MCP-`similarity_search` kan het meteen bevragen.

- Workbench → **Setup → Similarity → Create similarity index** (type: *Text*).
- Bron: de `bwb:tekst`-literals (evt. beperkt tot Artikel/Lid/Divisie).
- Na het bouwen levert `get_similarity_options` de indexnaam; `similarity_search` werkt met
  `{"query": …, "similarityIndex": "<naam>", "connectorType": "similarity", "repositoryId": "inning"}`.

#### Route A — uitgevoerd (`bwb_similarity`)
Aangemaakt via `POST /rest/similarity` (header `X-GraphDB-Repository: inning`), body:
- `name`: `bwb_similarity`
- `type`: `text`, `infer`: true, `sameAs`: true
- `analyzerClass`: `org.apache.lucene.analysis.nl.DutchAnalyzer`
- `options`: `-trainingcycles 5 -dimension 200`  (SemanticVectors — let op: `-dimension`, niet `-vectorsize`)
- `selectQuery`: `SELECT ?documentID ?documentText { ?documentID bwb:tekst ?documentText
  FILTER(STRSTARTS(STR(?documentID), "urn:bwb:")) }`  (eigen IRI-ruimte → geen sameAs-dubbels)
- `searchQuery`: de standaard similarity-template (`:searchTerm`/`:documentResult`/`:value`/`:score`).

Build duurde ~enkele seconden (native training over ~4000 literals). Herbouwen bij nieuwe/gewijzigde
tekst: DELETE + POST, of de Workbench-rebuild.

Kies dit als je **nu** semantiek wilt zonder infra. Later te vervangen door Route B.

### Route B — echte embeddings via de ChatGPT-Retrieval-connector (gekozen richting)
Hoogste kwaliteit: gebruik een modern embedding-model (Azure OpenAI `text-embedding-3-large`,
dezelfde Azure-resource als de LLM) en laat GraphDB de literals daar vectoriseren via de
**ChatGPT-Retrieval-connector** (die is in de Workbench-connectorlijst al zichtbaar, nog zonder
instance).

**Voorbereiding (Azure):**
1. In de Azure-AI-Foundry/OpenAI-resource een **embeddings-deployment** aanmaken:
   `text-embedding-3-large` (of `-small` voor lagere kosten). Noteer endpoint + deployment-naam + key.
2. Bepaal de vector-dimensie (3-large = 3072, 3-small = 1536) — die moet matchen met de connector-config.

**GraphDB-connector aanmaken** (Workbench → **Connectors → ChatGPT Retrieval → New instance**, of via
de `CREATE`-SPARQL van de connector). Kernvelden:
- naam: bv. `bwb_embeddings`;
- embeddings-endpoint + key + model = de Azure-deployment uit stap 1 (OpenAI-compatibel);
- te indexeren velden: `bwb:tekst` (+ optioneel `rdfs:label`), met de node-IRI als id;
- filter op type (Artikel/Lid/Divisie) om ruis/kosten te beperken.

> De exacte veldnamen verschillen per GraphDB-versie — volg de connector-UI en de GraphDB-docs
> ("ChatGPT Retrieval connector") voor 11.4. Test op een **kleine subset** (één regeling) vóór je
> de hele graaf vectoriseert i.v.m. embedding-kosten.

**Kosten/omvang:** ~1150 artikelen + ~2350 leden + ~800 divisies ≈ enkele duizenden literals →
eenmalige embedding-kosten zijn beperkt; alleen bij her-indexeren of nieuwe regelingen komt er bij.

## Graph-qa-kant (LIVE — route A)

De `semantic_search`-tool is **config-gedreven** en geactiveerd:
- **`SIMILARITY_INDEX=bwb_similarity`** in de env (`Settings.similarity_index`). Leeg = de tool geeft
  netjes "niet geconfigureerd" en de agent valt terug op `search_wetgeving` (geen crash).
- De tool roept de MCP-tool `similarity_search` aan met `{query, similarityIndex, connectorType:
  "similarity", repositoryId, limit}` (`agent/mcp_client.py:semantic_search`). De systeemprompt kent
  de hybride-zoekregel (exact vs. betekenis).
- **Eval:** `eval/golden.jsonl` bevat `requires: "semantic"`-cases; `eval/run_eval.py` slaat ze over
  zolang `SIMILARITY_INDEX` leeg is en meet ze zodra de index staat (nu: ze slagen).

**Route C (upgrade) later:** met een Azure OpenAI embeddings-deployment maak je een ChatGPT-Retrieval-
connector aan (Deel hierboven) en schakel je `mcp_client.semantic_search` om naar `retrieval_search`
met `connectorInstance` + `queryTemplate` (die tool eist `{queries, connectorInstance, repositoryId,
queryTemplate}`). De rest van de tool/agent blijft gelijk.

## Verificatie

- Route A: `get_similarity_options` (repo `inning`) geeft de indexnaam terug (nu `{}`).
- Route B: `Connectors`-lijst toont de ChatGPT-Retrieval-instance; `retrieval_search` met
  `connectorInstance` geeft treffers.
- Steekproef: een semantische query ("uitstel van betaling bij belastingschuld") vindt de
  relevante IW-bepaling zonder de exacte term.
