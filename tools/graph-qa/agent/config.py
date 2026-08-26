"""
Centrale configuratie: één gevalideerd Settings-model dat de omgeving één keer
inleest, zodat de rest van de code niet meer verspreid os.environ hoeft te raadplegen.

We gebruiken bewust een gewone pydantic BaseModel + from_env() i.p.v. pydantic-settings:
zelfde effect (validatie, één inleespunt), maar geen extra runtime-dependency.
De secrets zijn optioneel zodat import en /health blijven werken zonder volledige
config; de agent roept require_llm()/require_graph() aan zodra hij ze echt nodig heeft.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel


def _pakketversie() -> str:
    """De versie van deze agent, voor de herkomst bij een annotatie. Onbekend → lege string:
    liever geen versie dan een verzonnen versie."""
    try:
        from importlib.metadata import version

        return version("graph-qa")
    except Exception:
        return ""


def _read_secret(env: Mapping[str, str], name: str) -> str | None:
    """Lees een secret: eerst `<NAME>_FILE` (host-bestand, Docker-conventie), anders `<NAME>`."""
    path = env.get(name + "_FILE")
    if path:
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            return None
    return env.get(name)


class Settings(BaseModel):
    # GraphDB MCP
    graphdb_mcp_url: str = ""                  # verplicht; zie require_graph()
    graphdb_token: str | None = None
    repository_id: str = "inning"
    graphdb_sparql_tool: str = "sparql_query"  # naam van de SPARQL-tool op de MCP-server
    similarity_index: str = ""                 # GraphDB similarity-index voor semantic_search; leeg = uit

    # LLM (Azure AI Foundry / Anthropic)
    azure_foundry_api_key: str | None = None
    azure_foundry_base_url: str | None = None
    llm_model: str = "claude-sonnet-4-6"
    # Model per ROL. Leeg = `llm_model`, dus zonder deze env-vars draait alles zoals voorheen.
    #
    # De rollen in deze keten verschillen sterk in wat ze vragen: de router kiest uit twee workers
    # en drie specialisten binnen 300 tokens, en zijn antwoord wordt daarna toch hard gesaneerd
    # (`parse_supervisor`). De ophaal-agent zoekt een bepaling op met getypeerde tools. Dat is ander
    # werk dan het JAS-oordeel van de annoteerder en de Critic — en dáár mag je niet op besparen:
    # die twee blijven bewust op `llm_model`, zonder eigen knop, zodat niemand ze per ongeluk
    # degradeert. Een goedkopere Critic degradeert precies het oordeel waarvoor hij bestaat.
    #
    # De ophaal-agent is de gevaarlijkste om te verlagen: kiest hij de verkeerde bepaling, dan is
    # alles daarna brongetrouw én verkeerd, en dat ziet de jurist niet. Verlaag hem pas na meting
    # met `eval/run_eval.py`.
    llm_model_router: str = ""
    llm_model_ophaal: str = ""
    # Herkomst die met elke annotatie meereist: welk model/welke agentversie het voorstel maakte.
    # `llm_provider` is beschrijvend (de adapter praat via Azure AI Foundry met de Anthropic-SDK);
    # `agent_versie` komt uit de image-tag/env en valt terug op de pakketversie.
    llm_provider: str = "anthropic_via_azure_foundry"
    agent_versie: str = ""

    # Agent-loop
    max_turns: int = 20
    # Cap op de historie die per beurt naar de LLM gaat (tegen onbegrensde promptgroei in een lange
    # sessie). Char-budget; 0 = uit. Ruim genoeg dat de huidige vraag + tool-resultaten altijd passen.
    max_history_chars: int = 40000

    # De wetsanalyse-API: waar de uitkomst van een beurt wordt vastgelegd. Leeg = niet vastleggen
    # (dan schrijft de werkplek het weg, zoals vroeger) — zo blijft lokaal draaien zonder api mogelijk.
    wetsanalyse_api_url: str = ""
    wetsanalyse_api_token: str | None = None

    # API-laag
    qa_api_token: str | None = None
    cors_origins: list[str] = ["*"]
    rate_limit: int = 60          # verzoeken per venster (per proces, per IP)
    rate_window_seconds: float = 60.0
    # Achter een reverse proxy: de eerste X-Forwarded-For-hop als client-IP nemen voor de rate-limit.
    # Standaard uit (peer-IP), zodat een gespooft header de limiet niet omzeilt tenzij bewust aangezet.
    trust_proxy: bool = False

    # Orkestrator
    enable_planning: bool = True      # lichte plan-node vóór de agent (plan→retrieve→reason→verify)
    enable_memory_context: bool = True  # eerder geraadpleegde bepalingen als pointer-context injecteren

    # Decompositie (multi-hop): samengestelde vraag → deelvragen → retrieval per deelvraag → synthese.
    # Uit = de bestaande één-loop-stroom (byte-voor-byte ongewijzigd).
    enable_decomposition: bool = False
    max_subquestions: int = 5         # cap op het aantal deelvragen (kosten/latency begrenzen)
    sub_max_turns: int = 8            # agent⇄tools-beurten per deelvraag (los van max_turns)

    # Correctie na de Critic: **0 = uit**, **> 0 = aan**.
    #
    # LET OP — deze knop telt géén rondes meer, ondanks zijn naam. De keten ligt vast:
    # `annoteer → critic₁ → patch → [herzie] → [critic₂] → emit`, zonder cyclus. Er valt dus niets te
    # begrenzen; er valt alleen te kiezen of de correctiestap er is. De naam en de env-var
    # (`CRITIC_MAX_RONDES`) blijven bestaan zodat een draaiende deployment niet omvalt.
    #
    # Uit betekent exact het oude `annoteer → critic → emit` — de veiligheidsklep om dit zonder
    # rollback terug te draaien.
    critic_max_rondes: int = 2

    # Geheugen (LangGraph-checkpointer). Voorrang: `checkpoint_db_url` (Postgres, gedeeld → horizontaal
    # veilig) → anders `checkpoint_db_path` (durable AsyncSqliteSaver, per-instance) → anders in-memory.
    checkpoint_db_url: str | None = None
    checkpoint_db_path: str | None = "conversations_checkpoints.db"

    # Prompt-caching op het stabiele deel van de systeemprompt (identiteit, JAS-klassen,
    # specialist). Die blokken zijn groot en gaan per beurt meermaals identiek de deur uit — de
    # annotatieketen alleen al doet 3 tot 5 calls met dezelfde dertien-klassen-referentie. Uit te
    # zetten met `PROMPT_CACHING=false`; de adapter schakelt zichzelf bovendien uit zodra de
    # provider `cache_control` weigert (het is op Azure AI Foundry een beta-functie).
    prompt_caching: bool = True

    # Grounding
    # Bij een ongegrond antwoord één corrigerende her-vraag (`correct_node`), hoogstens één keer.
    #
    # Stond uit, en daarmee was de groundingcontrole een melding onder het antwoord en verder niets:
    # de jurist las een antwoord waarvan de keten zelf had vastgesteld dat er citaten in stonden die
    # niet in de bron voorkomen. Voor een platform waarvan brongetrouwheid het bestaansrecht is, is
    # signaleren te weinig zolang herstellen één call kost — en die call komt er alléén als er
    # werkelijk iets mis is. `GROUNDING_CORRECT=false` zet hem terug uit.
    grounding_correct: bool = True
    curate_sources: bool = True       # bronnenlijst beperken tot in het antwoord aangehaalde regelingen

    # Observability (gated op otel_endpoint; leeg = alleen JSON-logs)
    otel_endpoint: str = ""
    otel_service_name: str = "graph-qa"
    otel_metrics_enabled: bool = True
    log_format: str = "json"
    log_level: str = "info"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        e = env if env is not None else os.environ
        cors = [o.strip() for o in e.get("CORS_ORIGINS", "*").split(",") if o.strip()]
        raw: dict[str, object] = {
            "graphdb_mcp_url": e.get("GRAPHDB_MCP_URL"),
            "graphdb_token": _read_secret(e, "GRAPHDB_TOKEN"),
            "repository_id": e.get("GRAPHDB_REPOSITORY_ID"),
            "graphdb_sparql_tool": e.get("GRAPHDB_SPARQL_TOOL"),
            "similarity_index": e.get("SIMILARITY_INDEX"),
            "azure_foundry_api_key": _read_secret(e, "AZURE_FOUNDRY_API_KEY"),
            "azure_foundry_base_url": e.get("AZURE_FOUNDRY_BASE_URL"),
            "llm_model": e.get("LLM_MODEL"),
            "llm_model_router": e.get("LLM_MODEL_ROUTER"),
            "llm_model_ophaal": e.get("LLM_MODEL_OPHAAL"),
            "llm_provider": e.get("LLM_PROVIDER"),
            "agent_versie": e.get("AGENT_VERSION") or _pakketversie(),
            "max_turns": e.get("MAX_TURNS"),
            "max_history_chars": e.get("MAX_HISTORY_CHARS"),
            "enable_decomposition": e.get("ENABLE_DECOMPOSITION"),
            "max_subquestions": e.get("MAX_SUBQUESTIONS"),
            "sub_max_turns": e.get("SUB_MAX_TURNS"),
            "critic_max_rondes": e.get("CRITIC_MAX_RONDES"),
            "grounding_correct": e.get("GROUNDING_CORRECT"),
            "prompt_caching": e.get("PROMPT_CACHING"),
            "wetsanalyse_api_url": e.get("WETSANALYSE_API_URL"),
            "wetsanalyse_api_token": _read_secret(e, "WETSANALYSE_API_TOKEN"),
            "qa_api_token": _read_secret(e, "QA_API_TOKEN"),
            "cors_origins": cors or None,
            "rate_limit": e.get("QA_RATE_LIMIT"),
            "rate_window_seconds": e.get("QA_RATE_WINDOW_SECONDS"),
            "trust_proxy": e.get("TRUST_PROXY"),
            "otel_endpoint": e.get("OTEL_EXPORTER_OTLP_ENDPOINT"),
            "otel_service_name": e.get("OTEL_SERVICE_NAME"),
            "log_format": e.get("LOG_FORMAT"),
            "log_level": e.get("LOG_LEVEL"),
            "checkpoint_db_url": _read_secret(e, "CHECKPOINT_DB_URL"),
            "checkpoint_db_path": e.get("CHECKPOINT_DB_PATH"),
        }
        # None én lege string weglaten zodat de veld-defaults van kracht blijven (een gezet-maar-leeg
        # MAX_TURNS="" e.d. zou anders bij pydantic-coercie de import laten crashen i.p.v. de default te nemen)
        return cls(**{k: v for k, v in raw.items() if v is not None and v != ""})

    @property
    def legt_zelf_vast(self) -> bool:
        """Schrijft graph-qa de uitkomst van een beurt zelf weg?

        Zo ja, dan is een beurt niet meer afhankelijk van een browser die blijft kijken. Zo nee, dan
        blijft de werkplek dat doen — en dan is een gesloten tabblad nog steeds werkverlies."""
        return bool(self.wetsanalyse_api_url and self.wetsanalyse_api_token)

    def model_voor(self, rol: str) -> str:
        """Welk model draait deze rol? Onbekende of niet-ingestelde rol → `llm_model`.

        Alleen `router` en `ophaal` hebben een eigen knop; de annoteerder, de Critic en de
        QA-specialisten draaien per definitie op `llm_model`. Dat is geen omissie maar de grens:
        wie een oordeel velt over wetgeving krijgt het sterkste model, en dat hoort niet met een
        env-var te verzwakken.
        """
        return {"router": self.llm_model_router, "ophaal": self.llm_model_ophaal}.get(
            rol, ""
        ) or self.llm_model

    def require_api(self) -> None:
        """Kan graph-qa schrijven, dan MOET zijn eigen endpoint een token hebben.

        Zonder `QA_API_TOKEN` staat `/v1/runs` open (zie `_check_auth`), en dan is een open endpoint
        met een schrijfpad naar andermans gesprekken een gat: het verzoek draagt zelf de `user_id`
        waarnamens er geschreven wordt. Fail-fast bij boot in plaats van dat stil laten bestaan."""
        if self.legt_zelf_vast and not self.qa_api_token:
            raise ValueError(
                "graph-qa mag naar de wetsanalyse-API schrijven (WETSANALYSE_API_URL/_TOKEN), "
                "maar zijn eigen endpoint is open. Zet QA_API_TOKEN."
            )

    def controleer_historie_grens(self) -> None:
        """Waarschuw als het promptbudget de opslagrem raakt.

        `max_history_chars` begrenst wat er per beurt naar het model gaat; de reducer in de
        orkestrator begrenst wat er in de checkpointer blijft staan. Die tweede hoort ruim boven de
        eerste te liggen — anders snoeit de opslagrem binnen het venster dat de LLM tóch al krijgt,
        en verlies je context die je net wilde meegeven.
        """
        import logging

        from .orchestrator import MAX_HISTORIE_CHARS

        if self.max_history_chars * 2 > MAX_HISTORIE_CHARS:
            logging.getLogger("graph_qa.config").warning(
                "MAX_HISTORY_CHARS ligt dicht bij de opslaggrens van de checkpointer; "
                "verhoog MAX_HISTORIE_CHARS in orchestrator.py of verlaag dit budget",
                extra={"categorie": "technisch", "max_history_chars": self.max_history_chars,
                       "max_historie_chars": MAX_HISTORIE_CHARS},
            )

    def require_llm(self) -> None:
        if not self.azure_foundry_api_key or not self.azure_foundry_base_url:
            raise ValueError(
                "LLM niet geconfigureerd: zet AZURE_FOUNDRY_API_KEY en AZURE_FOUNDRY_BASE_URL."
            )

    def require_graph(self) -> None:
        if not self.graphdb_mcp_url:
            raise ValueError("Graaf niet geconfigureerd: zet GRAPHDB_MCP_URL.")
        if not self.graphdb_token:
            raise ValueError("Graaf niet geconfigureerd: zet GRAPHDB_TOKEN.")
