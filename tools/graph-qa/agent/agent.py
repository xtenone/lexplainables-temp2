"""
Agent-instap: dunne wrapper rond de LangGraph-orkestrator (agent/orchestrator.py).

Behoudt de publieke `answer_stream`-signatuur en het SSE-event-contract, zodat de API
en frontend ongewijzigd blijven. De stroom (plan→retrieve→reason→verify→finalize) en de
token-streaming leven in de toestandsgraaf.

Geheugen loopt via de LangGraph-checkpointer (thread_id = conversation_id). Backend-keuze
(voorrang): `checkpoint_db_url` → **Postgres** (AsyncPostgresSaver; gedeeld tussen replica's,
horizontaal veilig) → `checkpoint_db_path` → **SQLite** (durable file, maar per-instance) →
anders in-proces (MemorySaver). De wrapper reset per beurt de werkvelden en levert de nieuwe
user-message; de append-reducer plakt die aan de gepersisteerde historie.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from langgraph.errors import GraphRecursionError

from .agent_common import BeurtGestopt, run_sync
from .config import Settings
from .observability import get_tracer
from .ports import GraphPort, LLMPort

logger = logging.getLogger(__name__)


def _checkpointer_ctx(settings: Settings):
    """Async context manager die de gekozen checkpointer levert. Voorrang: Postgres (gedeeld →
    horizontaal veilig) → SQLite-bestand (durable, per-instance) → in-memory."""
    url = settings.checkpoint_db_url
    if url:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        @asynccontextmanager
        async def _pg():
            async with AsyncPostgresSaver.from_conn_string(url) as saver:
                await saver.setup()  # idempotent: maakt de checkpoint-tabellen als ze ontbreken
                yield saver

        return _pg()

    path = settings.checkpoint_db_path
    if path:
        p = Path(path)
        if not p.is_absolute():
            p = Path(__file__).parent.parent / p  # stabiel t.o.v. cwd (graph-qa-root)
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        return AsyncSqliteSaver.from_conn_string(str(p))

    from langgraph.checkpoint.memory import MemorySaver

    @asynccontextmanager
    async def _mem():
        yield MemorySaver()

    return _mem()


def _foutmelding(exc: Exception) -> str:
    """Wat de jurist te zien krijgt als een beurt sneuvelt — per soort fout iets anders.

    De provider-uitzonderingen worden op naam herkend in plaats van geïmporteerd: de anthropic-SDK
    is een optionele extra (`--extra llm`), en deze module hoort ook te draaien in een omgeving die
    hem niet heeft.
    """
    soort = type(exc).__name__
    if soort == "RateLimitError":
        return ("De modelprovider is momenteel overbelast. Probeer het over een halve minuut "
                "opnieuw — je vraag is niet verloren, hij is alleen niet uitgevoerd.")
    if soort in ("BadRequestError", "UnprocessableEntityError"):
        return ("Deze beurt paste niet binnen de grenzen van het model — meestal is het gesprek te "
                "lang geworden. Begin een nieuw gesprek of stel de vraag gerichter.")
    if soort in ("APIConnectionError", "APITimeoutError"):
        return ("Ik kon de modelprovider niet bereiken. Probeer het zo opnieuw; blijft het "
                "misgaan, dan staat de oorzaak in het server-log.")
    return ("Er ging iets mis bij het beantwoorden. Probeer het opnieuw; "
            "blijft het misgaan, dan staat de oorzaak in het server-log.")


def _recursielimiet(settings: Settings) -> int:
    """Hoeveel LangGraph-stappen één beurt hoogstens mag zetten.

    Dit was `max_turns * 2 + 10` — een formule van vóór de annotatieketen, die alleen de
    agent⇄tools-lus telde. Met de default (20 beurten) kwam één annotatie-worker die zijn
    beurtlimiet vol gebruikt al op ~49 van de 50 stappen, en een keten van twee workers ging er
    zeker overheen. De uitkomst was bovendien onleesbaar: `GraphRecursionError` viel in de generieke
    `except` hieronder en werd "Er ging iets mis", terwijl het werk van tientallen calls weg was.

    Nu volgt de limiet de topologie: per worker de agent⇄tools-lus (2 stappen per beurt) plus de
    vaste nodes eromheen (supervisor/annoteer/critic/emit/advance ≈ 6) plus de correctieketen, maal
    het maximum aantal workers (`supervisor._MAX_WORKERS`), met marge.

    Die correctieketen is een **vast** aantal stappen — `patch → herzie → critic` — en niet meer een
    lus die met `critic_max_rondes` meeschaalt. De instelling zegt alleen nog of hij aanstaat.

    Dit is een vangnet, geen kostenknop: de echte begrenzing is `max_turns`.
    """
    from .supervisor import _MAX_WORKERS

    per_worker = 2 * settings.max_turns + 6 + (3 if settings.critic_max_rondes > 0 else 0)
    return _MAX_WORKERS * per_worker + 10


async def delete_conversation(conversation_id: str, *, settings: Settings | None = None) -> None:
    """Wis het volledige agent-geheugen (checkpointer-thread) van één gesprek. Idempotent: een
    onbekende `conversation_id` is geen fout. Aangeroepen als de werkplek een gesprek verwijdert, zodat
    de inhoud niet in de checkpointer-DB achterblijft (privacy — parallel aan de API-berichten-delete)."""
    settings = settings or Settings.from_env()
    async with _checkpointer_ctx(settings) as saver:
        # Zorg dat de checkpoint-tabellen bestaan (SQLite maakt ze anders pas bij de eerste write →
        # adelete_thread op een verse DB zou "no such table" geven). Idempotent; Postgres deed dit al.
        setup = getattr(saver, "setup", None)
        if setup is not None:
            try:
                await setup()
            except Exception:  # noqa: BLE001 — MemorySaver e.d. hebben geen tabellen
                pass
        await saver.adelete_thread(conversation_id)


async def answer_stream(
    question: str,
    conversation_id: str | None = None,
    *,
    modus: str = "auto",
    context: Any = None,
    doel: Any = None,
    settings: Settings | None = None,
    llm: LLMPort | None = None,
    graph: GraphPort | None = None,
    stop_check: Callable[[], bool] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    Async generator die SSE-events yield:
      {"type": "status", "message": "..."}
      {"type": "token", "content": "..."}
      {"type": "sources", "sources": [...]}
      {"type": "grounding", "grounded": bool, "unsupported": [...]}
      {"type": "done"}
      {"type": "error", "message": "..."}
    """
    settings = settings or Settings.from_env()

    # Providers: injecteer voor tests, of bouw defaults uit Settings.
    try:
        if graph is None:
            from .adapters.graphdb_graph import make_graph

            graph = make_graph(settings)
        if llm is None:
            from .adapters.anthropic_llm import AnthropicLLM

            llm = AnthropicLLM(settings)
        await run_sync(graph.initialize)
    except Exception as exc:
        logger.warning("MCP-verbinding mislukt", exc_info=True)
        yield {"type": "error", "message": f"MCP-verbinding mislukt: {exc}"}
        if graph is not None:
            graph.close()
        return

    from .orchestrator import build_graph

    builder = build_graph(settings, llm, graph, stop_check=stop_check)
    thread_id = conversation_id or uuid.uuid4().hex
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": _recursielimiet(settings),
    }
    # Per beurt: nieuwe user-message (append-reducer) + reset van de werkvelden.
    init: dict[str, Any] = {
        "question": question,
        "messages": [{"role": "user", "content": question}],
        "modus": modus,
        "context": context.model_dump() if hasattr(context, "model_dump") else (context or {}),
        # Het doel dat de aanroeper meegaf — MOET mee in de reset, net als de annotatievelden
        # hieronder: bleef het staan, dan annoteert de vólgende vraag in dezelfde thread opnieuw
        # de vorige bepaling zonder dat iemand daarom vroeg.
        "opgegeven_doel": doel.model_dump() if hasattr(doel, "model_dump") else (doel or {}),
        "source_trace": [],
        "turns": 0,
        "corrected": False,
        "answer": "",
        "sub_questions": [],
        "sub_findings": [],
        # Een afwijzing geldt de vráág, niet het gesprek. Bleef deze vlag staan, dan werd elke
        # volgende beurt in dezelfde thread ook afgewezen — dezelfde soort fout als een blijvende
        # `critic_ronde` hieronder.
        "afwijzen": False,
        # Annotatie-velden: MOETEN mee in de reset. De checkpointer bewaart de state per thread, dus
        # zonder dit begint een tweede beurt met `critic_ronde` van de vorige annotatie en wordt de
        # herzieningslus overgeslagen. Het corpus hoort daar ook bij: zonder reset annoteert een
        # tweede vraag in hetzelfde gesprek tegen de tekst van de vórige bepaling — precies de
        # verwisseling die de gerichte ophaal moet uitsluiten.
        "corpus": "",
        "voorstellen": [],
        "verworpen_fragmenten": [],
        "critic_feedback": [],
        "critic_ontbrekend": [],
        "critic_gefaald": False,
        "critic_ronde": 0,
        "nieuw_ontbrekend": [],
        "gemeld_ontbrekend": [],
        "patch_toegepast": 0,
        "stop_reden": "",
    }

    tracer = get_tracer(__name__)
    grounded = True
    try:
        async with _checkpointer_ctx(settings) as saver:
            app = builder.compile(checkpointer=saver)
            with tracer.start_as_current_span("graph_qa.answer") as span:
                async for mode, chunk in app.astream(init, config=config, stream_mode=["custom", "values"]):
                    if mode == "custom":
                        yield chunk
                    elif mode == "values" and "grounded" in chunk:
                        grounded = chunk["grounded"]
                span.set_attribute("graph_qa.grounded", grounded)
                logger.info(
                    "antwoord klaar",
                    extra={"grounded": grounded, "chat_session_id": conversation_id or ""},
                )

            # Yield done BINNEN de checkpointer-context: anders kan AsyncSqliteSaver.__aexit__
            # (SQLite-commit/flush) de generator blokkeren vóórdat 'done' de client bereikt.
            if conversation_id:
                yield {"type": "conversation_id", "conversation_id": conversation_id}
            yield {"type": "done"}

    except BeurtGestopt:
        # Geen fout: de jurist vroeg om te stoppen en de graaf is op een nodegrens uitgestapt. Wat er
        # tot hier geëmit is, is gewoon geldig; de aanroeper legt het vast.
        logger.info(
            "beurt gestopt op verzoek",
            extra={"categorie": "functioneel", "chat_session_id": conversation_id or ""},
        )
        if conversation_id:
            yield {"type": "conversation_id", "conversation_id": conversation_id}
        yield {"type": "done"}
    except GraphRecursionError:
        # Eigen melding: dit is geen storing maar een beurt die te lang werd, en de gebruiker kan er
        # zelf iets mee (gerichter vragen). Onder de generieke tekst hieronder was niet te zien
        # waaróm er niets kwam.
        logger.warning(
            "beurt raakte de stappenlimiet",
            extra={"categorie": "functioneel", "chat_session_id": conversation_id or "",
                   "recursion_limit": config["recursion_limit"]},
        )
        yield {
            "type": "error",
            "message": "Deze beurt werd te lang en is afgebroken. Stel de vraag gerichter — "
                       "bijvoorbeeld met een specifiek artikel of lid.",
        }
    except Exception as exc:
        # Gesaniteerde melding naar de client, volledige fout alleen in het log — zoals de api dat
        # bij de modelprovider-test doet. De ruwe exception van een LLM- of MCP-fout bevat
        # request-details (endpoints, payload-fragmenten) die niet in de browser thuishoren.
        #
        # Wél onderscheid maken waar de gebruiker er iets mee kan. "Er ging iets mis" gooide drie
        # gevallen op één hoop die om verschillende dingen vragen: even wachten, korter vragen, of
        # een storing melden. De statusregels van deze agent zijn elders juist precies; een
        # foutmelding hoort dat ook te zijn.
        logger.error("agent-fout", exc_info=True)
        yield {"type": "error", "message": _foutmelding(exc)}
    finally:
        graph.close()
