"""
LangGraph-orkestrator: plan → retrieve → reason → verify → finalize.

LangGraph levert het toestandsgraaf-substraat (nodes, conditionele edges, streaming,
checkpointing); de domeinlogica blijft die van Fase 1/2 — de nodes roepen de bestaande
LLMPort/GraphPort, de typed tool-registry, provenance en grounding aan. Geen
langchain-chatmodel: Azure Foundry blijft via AnthropicLLM.

Geheugen zit in de state en wordt door de checkpointer (thread_id = conversation_id)
gepersisteerd: `messages` (episodisch, append-reducer) en `entities_seen` (de "in
beeld"-set geraadpleegde bepalingen, semantische/entiteit-tier). De wrapper compileert
`build_graph()` met de gekozen checkpointer.

Streaming loopt via LangGraph's custom-stream (get_stream_writer); answer_stream
consumeert het en houdt het SSE-contract gelijk. Nodes zijn synchroon (threadpool),
zodat de blocking LLM-/MCP-calls de event-loop niet blokkeren.
"""
from __future__ import annotations

import functools
import logging
import operator
import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Annotated, Any, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from .agent_common import BeurtGestopt, truncate
from .annotatie import (
    _verwerk, _verwerk_critic, demp_zelfweerspreking, komt_letterlijk_voor, pas_critic_toe,
    openstaand_voorstel, sleutel_van, vervang_ids_door_citaat,
)
from .artikel import artikel_corpus
from .annotatie_prompt import (
    annotatie_systeemprompt,
    annotatie_userprompt,
    critic_systeemprompt,
    critic_userprompt,
    herziening_systeemprompt,
    herziening_userprompt,
)
from .config import Settings
from .graph.results import parse_select
from .grounding import check_grounding, curate_sources
from .models import AgentRun
from .ports import GraphPort, LLMPort
from .prompts import SYSTEM_PROMPT
from .provenance import collect_sources
from .specialists import DEFAULT as DEFAULT_SPECIALIST
from .specialists import get as get_specialist
from .supervisor import SUPERVISOR_SYSTEM, parse_supervisor
from .tools import anthropic_schemas, dispatch

logger = logging.getLogger("graph_qa.orchestrator")


def _doel_uit_json(text: str) -> dict[str, str]:
    """Haal het doel ({bwbId,artikel,lid,nummer}) uit de JSON van de ophaal-agent — plat of onder een
    `doel`-sleutel."""
    import json

    s, e = text.find("{"), text.rfind("}")
    if s != -1 and e > s:
        try:
            data = json.loads(text[s : e + 1])
            if isinstance(data, dict):
                d = data.get("doel") if isinstance(data.get("doel"), dict) else data
                return {k: str(d.get(k, "")).strip() for k in ("bwbId", "artikel", "lid", "nummer", "citeertitel")}
        except json.JSONDecodeError:
            pass
    return {"bwbId": "", "artikel": "", "lid": "", "nummer": "", "citeertitel": ""}


def _kandidaten_uit_json(text: str) -> list[dict[str, str]]:
    """Haal de kandidaat-bepalingen uit de JSON van de ophaal-agent.

    Vraagt een jurist om een ONDERWERP ("annoteer alles over aansprakelijkheid van de bestuurder"),
    dan is er geen enkele bepaling aan te wijzen. De ophaal-agent zoekt er dan in de graaf naar en
    levert `{"kandidaten": [...]}` in plaats van een `doel`. Welke daarvan de werkvoorraad in gaan is
    een inhoudelijke keuze van de jurist — dus hier niets raden.
    """
    import json

    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e <= s:
        return []
    try:
        data = json.loads(text[s : e + 1])
    except json.JSONDecodeError:
        return []
    rij = data.get("kandidaten") if isinstance(data, dict) else None
    if not isinstance(rij, list):
        return []

    uit: list[dict[str, str]] = []
    gezien: set[tuple[str, str, str]] = set()
    for k in rij:
        if not isinstance(k, dict):
            continue
        kandidaat = {
            veld: str(k.get(veld, "")).strip()
            for veld in ("bwbId", "artikel", "lid", "citeertitel", "fragment")
        }
        if not (kandidaat["bwbId"] and kandidaat["artikel"]):
            continue
        sleutel = (kandidaat["bwbId"], kandidaat["artikel"], kandidaat["lid"])
        if sleutel in gezien:
            continue
        gezien.add(sleutel)
        uit.append(kandidaat)
    return uit[:8]


# --- meldingen over het samenspel -----------------------------------------------------------------
#
# De annotatieketen doet er 60-90 seconden over en stuurde daarin geen enkel event: de jurist keek
# naar een leeg scherm en zag het heen-en-weer tussen annoteerder en Critic niet. Deze regels vullen
# dat gat. Ze zijn pure functies zodat de bewoording te testen is zonder een hele graaf te draaien.

def _ontbrekend_sleutel(item: dict[str, Any]) -> str:
    """Identiteit van een gemeld gemist element: klasse + het genoemde fragment."""
    return f"{str(item.get('klasse', '')).strip()}|{' '.join(str(item.get('tekst', '')).split()).lower()}"


def _stap(writer: Any, actor: str, bericht: str) -> None:
    """Meld één stap in de keten: `Actor · wat er gebeurde`.

    Bestaat om het idioom af te dwingen. Zonder deze helper verzint elke node zijn eigen vorm — zo
    stonden er "Opgesplitst in 3 deelvragen." en "Annoteerder · 4 gegrond" naast elkaar, en waren er
    twee verschillende teksten voor dezelfde graafbevraging.
    """
    writer({"type": "status", "message": f"{actor} · {bericht}"})


def _toolregel(call: dict[str, Any]) -> str:
    """`get_lid(BWBR0004770, art. 9, lid 1)` — de tool mét waar hij naar kijkt.

    Alleen de tool-naam zei te weinig: bij drie opeenvolgende `get_lid`-aanroepen zag je niet dat het
    om verschillende bepalingen ging.
    """
    inp = call.get("input") or {}
    delen = [str(inp[k]).strip() for k in ("bwb_id", "artikel", "nummer", "lid", "query", "term")
             if str(inp.get(k, "")).strip()]
    return f"{call.get('name', '?')}({', '.join(truncate(d, 60) for d in delen)})" if delen else str(call.get("name", "?"))


def _annoteer_melding(voorstellen: list[Any], verworpen: list[Any]) -> str:
    """Wat de annoteerder opleverde, inclusief wat er sneuvelde en waarom."""
    regel = f"{len(voorstellen) + len(verworpen)} fragmenten, {len(voorstellen)} gegrond"
    if not verworpen:
        return regel
    per_reden: dict[str, int] = {}
    for v in verworpen:
        reden = getattr(v, "reden", "") or "onbekend"
        per_reden[reden] = per_reden.get(reden, 0) + 1
    uitleg = {"niet_letterlijk": "niet letterlijk", "ongeldige_klasse": "ongeldige klasse"}
    details = ", ".join(f"{n}× {uitleg.get(r, r)}" for r, n in per_reden.items())
    return f"{regel} — {len(verworpen)} verworpen ({details})"


def _critic_melding(
    oordelen: dict[str, Any],
    ontbrekend: list[Any],
    nieuw: int | None = None,
    gedempt: int = 0,
) -> str:
    """Tellingen per aandacht-niveau; de oordelen zelf staan al op de reviewkaarten."""
    telling: dict[str, int] = {}
    for o in oordelen.values():
        niveau = getattr(o, "aandacht", "") or "geen oordeel"
        telling[niveau] = telling.get(niveau, 0) + 1
    # Een gedempt oordeel staat als geel op de kaart. Het hier als rood tellen zou de tijdlijn iets
    # anders laten zeggen dan de jurist ziet — precies het soort verschil waarmee je deze keten
    # beoordeelt.
    if gedempt:
        telling["rood"] = max(0, telling.get("rood", 0) - gedempt)
        telling["geel"] = telling.get("geel", 0) + gedempt
        if not telling["rood"]:
            telling.pop("rood", None)
    volgorde = ["rood", "geel", "groen", "geen oordeel"]
    delen = [f"{telling[n]} {n}" for n in volgorde if telling.get(n)]
    regel = ", ".join(delen) if delen else "geen oordelen"
    if gedempt:
        woord = "oordeel" if gedempt == 1 else "oordelen"
        regel += f" · {gedempt} {woord} over een eigen correctie: als twijfel voorgelegd"
    if ontbrekend:
        regel += f" · {len(ontbrekend)} mogelijk gemist"
        # Onderscheid maken tussen "hij ziet iets nieuws" en "hij herhaalt zichzelf" is precies wat
        # je wilt kunnen zien in de tijdlijn.
        if nieuw is not None and nieuw < len(ontbrekend):
            regel += f" ({nieuw} nieuw)" if nieuw else " (niets nieuws)"
    return regel


def _grounding_melding(report: Any) -> str:
    """Wat de brongetrouwheidstoets opleverde — inclusief het geval dat er niets te toetsen viel.

    De controle kijkt naar twee dingen die los van elkaar staan: **vindplaatsen** (BWB-id's en IRI's
    in het antwoord) en **citaten** (tekst tussen aanhalingstekens). De melding hoort te zeggen wat
    er daadwerkelijk is nagelopen.

    Dat ging mis bij een antwoord dat artikelen in gewone taal noemt — "artikel 2 lid 1 onderdeel m"
    zonder BWB-id. Nul vindplaatsen dus, maar wél twee citaten, en die klopten allebei. De tijdlijn
    meldde toen "0 verwijzingen onderbouwd": precies de misleidende regel die de "niets te
    controleren"-tak hierboven had moeten voorkomen, maar die vangt alleen het geval waarin er
    helemaal niets was.
    """
    if report.niveau == "onbepaald":
        return "brongetrouwheid: geen vindplaats of citaat genoemd — niets te controleren"

    delen: list[str] = []
    if report.unsupported:
        delen.append(f"{len(report.unsupported)} verwijzing(en) niet uit de graaf")
    if report.niet_letterlijk:
        delen.append(f"{len(report.niet_letterlijk)} citaat(en) niet letterlijk teruggevonden")
    if delen:
        return "brongetrouwheid: " + ", ".join(delen)

    # Alles klopte. Zeg dan wát er klopte, en tel alleen mee wat er ook echt was.
    aantal_citaten = int(getattr(report, "citaten", 0) or 0)
    goed: list[str] = []
    if report.cited:
        goed.append(f"{len(report.cited)} " + ("verwijzingen" if len(report.cited) > 1 else "verwijzing"))
    if aantal_citaten:
        goed.append(f"{aantal_citaten} " + ("citaten" if aantal_citaten > 1 else "citaat"))
    return f"brongetrouwheid: {' en '.join(goed)} gecontroleerd"


def _herzien_melding(voor: list[dict[str, Any]], na: list[dict[str, Any]]) -> str:
    """Wat de annoteerder met de kritiek deed. Dít is het samenspel: aangepast versus behouden."""
    oud = {v.get("id"): v for v in voor}
    aangepast = sum(
        1 for v in na
        if v.get("id") in oud
        and any(oud[v["id"]].get(k) != v.get(k) for k in ("klasse", "tekst", "lid"))
    )
    ongewijzigd = sum(1 for v in na if v.get("id") in oud) - aangepast
    toegevoegd = sum(1 for v in na if v.get("id") not in oud)
    verdwenen = sum(1 for v in voor if v.get("id") not in {x.get("id") for x in na})
    delen = [f"{aangepast} aangepast", f"{ongewijzigd} ongewijzigd"]
    if toegevoegd:
        delen.append(f"{toegevoegd} toegevoegd")
    if verdwenen:
        delen.append(f"{verdwenen} verwijderd")
    return ", ".join(delen)


def _doel_uit_toolcalls(messages: list[dict[str, Any]]) -> dict[str, str]:
    """Gezaghebbend doel = de LAATSTE fetch-tool-call (get_lid/get_artikel/get_bepaling) die de agent
    deed — wat hij écht ophaalde. get_bepaling levert een `nummer` (bv. '9.1' voor een divisie); dat
    zetten we óók als `artikel`, zodat de weergave het aankan. Leeg als er geen fetch-call was."""
    doel = {"bwbId": "", "artikel": "", "lid": "", "nummer": ""}
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for blok in content:
            if not (isinstance(blok, dict) and blok.get("type") == "tool_use"):
                continue
            naam = blok.get("name")
            inp = blok.get("input") or {}
            if naam in ("get_lid", "get_artikel"):
                doel = {
                    "bwbId": str(inp.get("bwb_id", "")).strip(),
                    "artikel": str(inp.get("artikel", "")).strip(),
                    "lid": str(inp.get("lid", "")).strip(),
                    "nummer": "",
                }
            elif naam == "get_bepaling":
                nummer = str(inp.get("nummer", "")).strip()
                doel = {"bwbId": str(inp.get("bwb_id", "")).strip(), "artikel": nummer, "lid": "", "nummer": nummer}
    return doel


def _bepaal_doel(state: State) -> dict[str, str]:
    """Combineer: neem de tool-call als bron (gezaghebbend) en vul lege velden aan uit de JSON.

    Gaf de aanroeper zélf een doel mee, dan wint dat van allebei: dan hoefde er niets gezocht te
    worden en is dit precies de bepaling die de jurist aanwees. De andere twee bronnen blijven als
    aanvulling staan — zo vult een meegegeven `{bwbId, artikel}` zich alsnog met een `citeertitel`
    als die uit de trace komt.
    """
    opgegeven = state.get("opgegeven_doel") or {}
    uit_tool = _doel_uit_toolcalls(state.get("messages", []))
    uit_json = _doel_uit_json(state.get("answer", ""))
    return {
        k: str(opgegeven.get(k, "") or "").strip() or uit_tool.get(k, "") or uit_json.get(k, "")
        for k in ("bwbId", "artikel", "lid", "nummer", "citeertitel")
    }


def _heeft_opgegeven_doel(state: State) -> bool:
    """Kunnen we meteen annoteren? Alleen met bwbId én een aanduiding is het doel compleet."""
    doel = state.get("opgegeven_doel") or {}
    return bool(str(doel.get("bwbId", "")).strip()
                and (str(doel.get("artikel", "")).strip() or str(doel.get("nummer", "")).strip()))


def _corpus_uit_trace(source_trace: list[tuple[str, str]]) -> str:
    """Reconstrueer de opgehaalde artikeltekst uit de get_lid/get_artikel-resultaten in de trace.

    **Terugval, geen eerste keus** — zie `_corpus_voor_doel`. Deze reconstructie plakt álle
    fetch-resultaten van de beurt aaneen, terwijl het doel de láátste fetch-call is: haalde de
    ophaal-agent eerst het hele artikel op en daarna het gevraagde lid, dan zit de tekst van de
    andere leden er ook in — en dan keurt de brongetrouwheidscheck een fragment uit lid 2 goed als
    markering "in lid 1". Bovendien is elk tool-resultaat afgekapt op 8000 tekens (`truncate`),
    dus bij een lange bepaling ontbreekt hier stilzwijgend het staartstuk.
    """
    delen: list[str] = []
    for naam, resultaat in source_trace:
        if naam not in ("get_lid", "get_artikel", "get_bepaling"):
            continue
        for r in parse_select(resultaat):
            tekst = (r.get("lidtekst") or r.get("tekst") or "").strip()
            if tekst:
                delen.append(tekst)
    return "\n\n".join(delen)


def _corpus_voor_doel(doel: dict[str, str], graph: GraphPort, source_trace: list[tuple[str, str]]) -> str:
    """De tekst waarop geannoteerd wordt: precies de bepaling uit `doel`, ongekapt.

    Eén gerichte ophaalactie via `artikel.artikel_corpus` — dezelfde functie waarmee `GET /v1/artikel`
    het documentpaneel vult. Daarmee is er weer één bron voor wat de jurist ziet en waartegen de
    brongetrouwheid wordt gecheckt, zoals `agent/artikel.py` altijd al beloofde.

    Kost één extra SPARQL-call per annotatiebeurt. Dat is de prijs voor een corpus dat niet afhangt
    van hoeveel omwegen de ophaal-agent nam; het resultaat gaat in de state, dus Critic en herziening
    betalen hem niet opnieuw.

    Levert de graaf niets (of kennen we het doel niet), dan valt dit terug op de trace-reconstructie:
    liever de tekst die de agent zag dan helemaal geen corpus — dan zou de hele beurt afbreken.
    """
    bwb = (doel.get("bwbId") or "").strip()
    aanduiding = (doel.get("artikel") or doel.get("nummer") or "").strip()
    if bwb and aanduiding:
        try:
            corpus = artikel_corpus(bwb, aanduiding, graph, (doel.get("lid") or "").strip() or None)
            if corpus.strip():
                return corpus
            logger.info(
                "corpus: graaf gaf niets voor het doel; terugval op de tool-trace",
                extra={"bwb_id": bwb, "aanduiding": aanduiding, "lid": doel.get("lid", "")},
            )
        except Exception:  # noqa: BLE001 — een mislukte ophaal mag de annotatie niet breken
            logger.warning("corpus: gericht ophalen mislukt; terugval op de tool-trace", exc_info=True)
    return _corpus_uit_trace(source_trace)

_DECOMPOSE_SYSTEM = (
    "Je splitst een juridische vraag over de kennisgraaf op in de deelvragen die je apart moet "
    "beantwoorden om de hele vraag te dekken. Geef ELKE deelvraag op een eigen regel, genummerd "
    "(1., 2., …), in logische volgorde (een deelvraag mag voortbouwen op een eerdere). Splits ALLEEN "
    "als de vraag echt meerdere losse onderdelen heeft; een enkelvoudige vraag geef je als één regel "
    "terug (de vraag zelf). Verzin geen deelvragen die niet in de oorspronkelijke vraag besloten "
    "liggen. Geen inleiding of uitleg — alleen de genummerde regels."
)

_SYNTHESE_SYSTEM = (
    "Je stelt één samenhangend eindantwoord samen uit de per-deelvraag verzamelde bevindingen. "
    "Steun UITSLUITEND op die bevindingen — voeg geen nieuwe feiten toe en verzin geen vindplaatsen. "
    "Behoud de vindplaatsen (regeling/artikel/lid) letterlijk zoals ze in de bevindingen staan. "
    "Antwoord bondig en goed gestructureerd; adresseer elk onderdeel van de oorspronkelijke vraag."
)


def _parse_final(final: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """Splits een Anthropic-response in (tool_uses, text_parts)."""
    tool_uses: list[dict[str, Any]] = []
    text_parts: list[str] = []
    for block in final.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_uses.append({"id": block.id, "name": block.name, "input": block.input})
    return tool_uses, text_parts


def _msg_lengte(m: dict[str, Any]) -> int:
    c = m.get("content")
    if isinstance(c, str):
        return len(c)
    if isinstance(c, list):
        return sum(len(str(b)) for b in c)
    return 0


def _is_tool_result_user(m: dict[str, Any]) -> bool:
    """Een user-message dat (alleen) tool_result-blokken draagt — orphan als z'n tool_use is weggevallen."""
    c = m.get("content")
    return (
        m.get("role") == "user"
        and isinstance(c, list)
        and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c)
    )


def _is_plain_user(m: dict[str, Any]) -> bool:
    """Een 'platte' user-beurt (de vraag/correctie) — géén tool_result-drager. Zo'n bericht is een
    geldig venster-begin: alles erna is een compleet assistant→tool_result-verloop."""
    return m.get("role") == "user" and not _is_tool_result_user(m)


def _trim_messages(messages: list[dict[str, Any]], max_chars: int) -> list[dict[str, Any]]:
    """Beperk de historie die naar de LLM gaat tot een char-budget, met behoud van de
    tool_use/tool_result-integriteit (Anthropic weigert een orphan tool_result).

    Neem het achterste venster binnen budget en breid het begin zo nodig terug uit tot een platte
    user-beurt, zodat elk tool_result zijn tool_use behoudt (Anthropic weigert een orphan). Omdat
    messages[0] altijd een platte user-vraag is, termineert dat en is het resultaat nooit leeg;
    correctheid gaat daarbij boven het strikte char-budget. `max_chars<=0` → ongewijzigd.
    """
    if max_chars <= 0 or not messages:
        return messages
    total = 0
    start = 0
    for i in range(len(messages) - 1, -1, -1):
        total += _msg_lengte(messages[i])
        start = i
        if total >= max_chars:
            break
    # Loop terug over losgeknipte assistant/tool_result-berichten tot een geldig venster-begin
    # (een platte user-beurt), zodat er geen orphan tool_result vooraan blijft staan.
    while start > 0 and not _is_plain_user(messages[start]):
        start -= 1
    return messages[start:]


# Bovengrens op wat er in de CHECKPOINTER blijft staan. `max_history_chars` begrenst alleen wat er
# per beurt naar het model gaat; de opgeslagen historie groeide onbeperkt door, inclusief elk
# tool-resultaat van 8000 tekens. Bij een lang gesprek betekent dat een steeds tragere en dikkere
# checkpoint-write bij élke stap van de graaf.
#
# Ruim boven het prompt-budget gekozen (een veelvoud), zodat het snoeien nooit het venster raakt dat
# de LLM tóch al krijgt: dit is een opslagrem, geen tweede contextrem.
# Vaste grens, want een LangGraph-reducer is een pure functie zonder toegang tot `Settings`. Ruim
# vier keer het default prompt-budget (`max_history_chars`, 40k). Zet iemand dat budget hoger dan de
# helft hiervan, dan waarschuwt `Settings.controleer_historie_grens()` bij boot — dan zou de
# opslagrem binnen het promptvenster gaan knippen, en dat is precies wat hij niet moet doen.
MAX_HISTORIE_CHARS = 160_000


def _snoei_historie(messages: list[dict[str, Any]], max_chars: int) -> list[dict[str, Any]]:
    """Houd de bewaarde historie onder een bovengrens, en knip alleen op een veilige grens.

    "Veilig" is een plátte user-beurt (`_is_plain_user`): begint de historie met een los
    tool_result, dan mist dat blok zijn tool_use en weigert Anthropic de hele request. Vinden we geen
    veilige grens binnen het budget, dan snoeien we níét — een te grote historie is hinderlijk, een
    kapotte is fataal.
    """
    if max_chars <= 0 or not messages:
        return messages
    totaal = sum(_msg_lengte(m) for m in messages)
    if totaal <= max_chars:
        return messages
    # Zoek van achter naar voren de eerste platte user-beurt die het geheel binnen budget brengt.
    opgeteld = 0
    for i in range(len(messages) - 1, -1, -1):
        opgeteld += _msg_lengte(messages[i])
        if opgeteld >= max_chars:
            for j in range(i, len(messages)):
                if _is_plain_user(messages[j]):
                    return messages[j:]
            return messages
    return messages


def _voeg_toe_en_snoei(
    bestaand: list[dict[str, Any]], nieuw: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """State-reducer voor `messages`: append (zoals `operator.add`) plus een opslagrem."""
    return _snoei_historie(list(bestaand) + list(nieuw), MAX_HISTORIE_CHARS)


def _schoon_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip lege tekstblokken (Anthropic weigert {"type":"text","text":""} — Claude stuurt die soms
    mee náást een tool_use; via het gespreksgeheugen komen ze terug). Berichten waarvan de content
    daardoor leeg wordt, slaan we over; tool_use/tool_result en string-content blijven ongemoeid."""
    schoon: list[dict[str, Any]] = []
    for m in messages:
        c = m.get("content")
        if isinstance(c, list):
            nieuw = [
                b
                for b in c
                if not (isinstance(b, dict) and b.get("type") == "text" and not str(b.get("text", "")).strip())
            ]
            if nieuw:
                schoon.append({**m, "content": nieuw})
        else:
            schoon.append(m)
    return schoon


class State(TypedDict, total=False):
    question: str
    # Episodisch geheugen, gepersisteerd door de checkpointer. De reducer voegt toe én snoeit: zonder
    # dat groeide de bewaarde historie onbeperkt door (inclusief elk tool-resultaat van 8000 tekens),
    # en werd elke checkpoint-write in een lang gesprek trager en dikker. Snoeien gebeurt alleen op
    # een platte user-beurt — een losgeknipt tool_result zou de volgende beurt laten crashen.
    messages: Annotated[list[dict[str, Any]], _voeg_toe_en_snoei]
    entities_seen: Annotated[list[str], operator.add]            # semantisch/entiteit-tier
    specialist: str
    plan: str
    worker_plan: list[str]   # geordende worker-keten (specialist-namen) die de supervisor koos
    afwijzen: bool           # supervisor plaatste de vraag buiten de scope → geen worker draait
    worker_idx: int          # index van de huidige worker in worker_plan
    source_trace: list[tuple[str, str]]
    answer: str
    grounded: bool
    cited: int
    unsupported: list[str]
    niet_letterlijk: list[str]   # als citaat gepresenteerd, maar niet letterlijk in de trace
    grounding_niveau: str        # gegrond | onbepaald | ongegrond
    sources: list[dict[str, Any]]
    pending_tools: list[dict[str, Any]]
    turns: int
    corrected: bool
    # Decompositie (multi-hop): deelvragen + per-deelvraag bevindingen (last-value-wins;
    # solve_node zet ze in één keer). De per-deelvraag agent⇄tools-loop draait lokaal in solve_node.
    sub_questions: list[str]
    sub_findings: list[dict[str, str]]
    # Het doel dat de AANROEPER meegaf ({bwbId, artikel, lid?, citeertitel?}). Weet de werkplek de
    # bepaling al — een open document, een item uit de werkvoorraad, een gekozen kandidaat — dan
    # hoeft niemand hem meer te zoeken: de supervisor doet geen LLM-call en de ophaal-agent draait
    # helemaal niet. Dat scheelt niet alleen calls; het verwijdert de gevaarlijkste faalmodus uit
    # die route, want een ophaal-agent die de verkeerde bepaling kiest levert werk op dat
    # brongetrouw én verkeerd is.
    opgegeven_doel: dict[str, str]
    # De tekst waarop deze annotatiebeurt draait: gericht opgehaald door annoteer_node (zie
    # `_corpus_voor_doel`) en daarna hergebruikt door de Critic en de herziening, zodat alle drie
    # over exact dezelfde bepaling oordelen én er maar één ophaalactie nodig is.
    corpus: str
    # Annotatie: de gegronde voorstellen (als dicts) die annoteer_node maakt; critic_node scoort ze
    # met een aandacht-niveau en emit ze dán pas als `element`-events.
    #
    # Alle annotatie-velden zijn last-value-wins (géén operator.add-reducer): elke node levert de
    # volledige lijst. Met een append-reducer zou de Critic-feedback over rondes heen stapelen en
    # zou een herziening zijn eigen vorige oordeel als actueel aanzien.
    voorstellen: list[dict[str, Any]]
    verworpen_fragmenten: list[dict[str, Any]]   # niet-gegronde citaten, als feedback voor een herziening
    critic_feedback: list[dict[str, Any]]        # [{id, aandacht, motivatie, actie, voorstel_*}]
    critic_ontbrekend: list[dict[str, Any]]
    critic_gefaald: bool
    critic_ronde: int                            # welke Critic-pas: 1 = oordeel, 2 = eindbeoordeling
    # Convergentie. Zonder deze drie draait de lus altijd tot de rondelimiet: de Critic bedenkt elke
    # ronde opnieuw wat er "mist", dus er is altijd een reden om door te gaan.
    nieuw_ontbrekend: list[dict[str, Any]]       # gemist én nog niet eerder gemeld — alleen dit is werk
    gemeld_ontbrekend: list[str]                 # sleutels van alles wat al ooit gemeld is
    patch_toegepast: int                         # hoeveel Critic-aanwijzingen de patcher uitvoerde
    stop_reden: str                              # waaróm de lus eindigde; komt in de tijdlijn
    # Wat de werkplek meestuurt over de bepaling/markering die in beeld staat. `modus == "advies"`
    # betekent: een vraag bij een bestaande annotatie, die niets mag wijzigen.
    modus: str
    context: dict[str, Any]


def build_graph(
    settings: Settings,
    llm: LLMPort,
    graph: GraphPort,
    stop_check: Callable[[], bool] | None = None,
) -> StateGraph:
    """Bouw de (ongecompileerde) toestandsgraaf; de wrapper compileert 'm met een checkpointer."""
    # `model` is het sterke model: annoteerder, Critic, herziener en de QA-specialisten. De router
    # en de ophaal-agent mogen apart worden gezet (`Settings.model_voor`); staat er niets, dan is
    # het alle drie hetzelfde en draait de keten exact als voorheen.
    model = settings.llm_model
    model_router = settings.model_voor("router")
    model_ophaal = settings.model_voor("ophaal")

    def _memory_context(state: State) -> str:
        if not settings.enable_memory_context:
            return ""
        seen = list(dict.fromkeys(state.get("entities_seen") or []))  # dedup, volgorde behouden
        if not seen:
            return ""
        lijst = "\n".join(f"- {u}" for u in seen[-12:])
        return (
            "\n\nGESPREKSCONTEXT — eerder in dit gesprek geraadpleegde bepalingen (alléén als "
            "aanknopingspunt voor verwijzingen als 'dat artikel'; verifieer elk feit opnieuw via "
            f"de tools):\n{lijst}"
        )

    def _corpus(state: State) -> str:
        """De tekst van deze annotatiebeurt. `annoteer_node` haalde hem gericht op en zette hem in de
        state; de terugval is er voor een state van vóór dit veld (een hervatte thread)."""
        return state.get("corpus") or _corpus_uit_trace(state.get("source_trace", []))

    def supervisor_node(state: State) -> dict[str, Any]:
        """Bepaalt de worker-keten (antwoord/annotatie) voor deze vraag; zet de eerste worker actief."""
        writer = get_stream_writer()

        if _heeft_opgegeven_doel(state):
            # De aanroeper weet welke bepaling geannoteerd moet worden. Dan is er niets te kiezen en
            # niets te zoeken: geen supervisor-call, en `_entry_node` slaat de ophaal-agent over.
            # Wat de router zou beslissen is hier al bekend, en wat de ophaal-agent zou vinden staat
            # er al — inclusief de zekerheid dat het de bepaling is die de jurist aanwees.
            doel = state.get("opgegeven_doel") or {}
            aanduiding = doel.get("artikel") or doel.get("nummer") or ""
            _stap(writer, "Lex", f"annoteert de aangewezen bepaling (art. {aanduiding})")
            return {
                "specialist": "annotatie", "worker_plan": ["annotatie"], "worker_idx": 0,
                "plan": "annotatie van een aangewezen bepaling", "afwijzen": False,
            }

        if state.get("modus") == "advies":
            # Een adviesvraag bij een bestaande annotatie: geen LLM-keuze, hard naar de
            # duiding-specialist. Dat is een topologische garantie in plaats van een belofte in een
            # prompt — de antwoord-route emit geen `doel`/`element`-events, dus advies vragen kán de
            # annotatie niet wijzigen. Scheelt bovendien een LLM-call.
            _stap(writer, "Lex", "advies bij een bestaande markering")
            return {
                "specialist": "duiding", "worker_plan": ["duiding"], "worker_idx": 0,
                "plan": "adviesvraag bij een bestaande annotatie",
            }

        resp = llm.create(
            model=model_router,
            max_tokens=300,
            system=SUPERVISOR_SYSTEM + _memory_context(state),
            tools=[],
            messages=[{"role": "user", "content": state["question"]}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        worker_plan, plan, afwijzen = parse_supervisor(text)
        if afwijzen:
            # Buiten de scope. Dit hoort hier te eindigen en niet als "AANPAK: AFWIJZEN" de
            # systeemprompt van een specialist in te gaan, waar een tweede modelbeslissing bepaalt
            # wat er gebeurt — dat kost minstens één extra call en is bovendien geen garantie.
            _stap(writer, "Supervisor", "buiten de wet- en regelgeving in de graaf")
            return {"specialist": "", "plan": plan, "worker_plan": [], "worker_idx": 0,
                    "afwijzen": True}
        eerste = worker_plan[0]
        _stap(writer, "Supervisor", f"kiest de {eerste}-worker · {plan[:80]}")
        return {"specialist": eerste, "plan": plan, "worker_plan": worker_plan, "worker_idx": 0,
                "afwijzen": False}

    def _entry_node(state: State) -> str:
        """Ingang voor de huidige worker: de annotatie-worker draait altijd de agent⇄tools-lus; een
        antwoord-worker gaat in decompositie-modus langs decompose, anders ook langs de agent-lus.

        Wees de vraag afgewezen, dan gaat er geen enkele worker draaien — dat is de hele winst."""
        if state.get("afwijzen"):
            return "afwijzen"
        if state.get("specialist") == "annotatie":
            # Doel al bekend → recht naar de annoteerder; de agent⇄tools-lus zou alleen opzoeken
            # wat de aanroeper al meestuurde. `annoteer_node` haalt het corpus zelf gericht op.
            return "annoteer" if _heeft_opgegeven_doel(state) else "agent"
        return "decompose" if settings.enable_decomposition else "agent"

    def advance_node(state: State) -> dict[str, Any]:
        """Ga naar de volgende worker in de keten; reset de per-worker werkvelden."""
        idx = state.get("worker_idx", 0) + 1
        plan = state.get("worker_plan") or []
        upd: dict[str, Any] = {"worker_idx": idx}
        if idx < len(plan):
            upd.update({
                "specialist": plan[idx], "turns": 0, "corrected": False, "answer": "",
                # Ook de annotatie-velden: een volgende worker begint schoon, anders zou een
                # tweede annotatie in dezelfde beurt op de rondeteller van de eerste doorbouwen.
                "voorstellen": [], "verworpen_fragmenten": [], "critic_feedback": [],
                "critic_ontbrekend": [], "critic_gefaald": False, "critic_ronde": 0,
                "nieuw_ontbrekend": [], "gemeld_ontbrekend": [], "patch_toegepast": 0,
                "stop_reden": "",
            })
        return upd

    def route_after_advance(state: State) -> str:
        plan = state.get("worker_plan") or []
        if state.get("worker_idx", 0) < len(plan):
            return _entry_node(state)
        return "einde"

    def _advies_context(state: State) -> str:
        """Contextblok voor een adviesvraag: waar gaat het over, en wat mag de agent niet doen.

        De 'wijzig niets'-instructie is hier een toelichting, geen slot — dat slot is topologisch
        (deze route emit geen element-events). Het staat er zodat het antwoord de juiste vorm heeft:
        een onderbouwing, geen voorstel voor een nieuwe annotatie.
        """
        if state.get("modus") != "advies":
            return ""
        c = state.get("context") or {}
        regels = ["", "--- WAAR DE VRAAG OVER GAAT ---"]
        plek = " ".join(x for x in (c.get("bwbId", ""), f"art. {c['artikel']}" if c.get("artikel") else "",
                                    f"lid {c['lid']}" if c.get("lid") else "") if x)
        if plek:
            regels.append(f"Bepaling: {plek}")
        if c.get("klasse"):
            regels.append(f"Voorgestelde JAS-klasse: {c['klasse']}")
        if c.get("fragment"):
            regels.append(f'Fragment: "{c["fragment"]}"')
        if c.get("corpus"):
            regels.append(f"\nArtikeltekst:\n{truncate(str(c['corpus']), 6000)}")
        regels += [
            "--- EINDE ---",
            "",
            "Dit is een ADVIESVRAAG bij een bestaande JAS-annotatie. Geef uitsluitend onderbouwing en "
            "duiding; stel geen nieuwe annotatie voor en zeg niet dat je iets hebt gewijzigd.",
        ]
        # Zonder deze afbakening motiveert het model álle markeringen die het in de gesprekshistorie
        # ziet staan — de annotatiebeurt zit immers in dezelfde thread. Wie één element aanklikt en
        # "motiveer" vraagt, verwacht één motivering. De laatste zin is de tegenkracht tegen dat
        # geheugen: zonder die toevoeging pakt het model er alsnog zijn eerdere voorstellen bij.
        if c.get("fragment"):
            buren = [b for b in (c.get("bestaande_elementen") or []) if isinstance(b, dict)]
            regels += [
                "",
                # Niet "ONDERWERP": dat woord gebruikt de basis-systeemprompt al voor de
                # onderwerp-afbakening van de agent (wel/geen wetgevingsvraag).
                f'AFBAKENING VAN DEZE VRAAG — het gaat over dit ene fragment: "{c["fragment"]}". '
                "Motiveer alleen dat element.",
                "Een andere markering uit dezelfde bepaling mag je erbij halen wanneer die NODIG is om "
                "dit element te onderbouwen — samenhang, afbakening, of het rechtsgevolg waar een "
                "voorwaarde bij hoort. Houd dat kort en breng het terug naar het onderwerp.",
                "Geef die andere markeringen GEEN eigen motivering, ook niet als je ze eerder in dit "
                "gesprek hebt voorgesteld.",
            ]
            if buren:
                # Meesturen in plaats van op het geheugen vertrouwen: anders hangt het antwoord af van
                # wat er toevallig nog in de historie stond, en verschilt het per gesprek.
                regels += [
                    "",
                    "--- ANDERE MARKERINGEN IN DEZE BEPALING (niet motiveren; alleen ter ondersteuning) ---",
                ]
                for b in buren[:20]:
                    klasse = str(b.get("klasse", "")).strip()
                    tekst = truncate(str(b.get("tekst", "")).strip(), 200)
                    if klasse and tekst:
                        regels.append(f'{klasse} — "{tekst}"')
                regels.append("--- EINDE ---")
        return "\n".join(regels)

    def afwijs_node(state: State) -> dict[str, Any]:
        """De supervisor plaatste de vraag buiten de wetgeving: hier eindigt de beurt.

        Kort en zonder verwijt, met de uitnodiging erbij — een afwijzing die alleen "dat doe ik niet"
        zegt laat iemand raden wat dan wel kan. Geen tools, geen bronnen, geen tweede LLM-call.

        Deze tekst zegt bewust NIET "staat niet in mijn kennisgraaf". Dit pad is er voor vragen die
        buiten de wetgeving vallen (het weer, programmeren), en dat weet de supervisor zonder te
        kijken. Of een bepáálde regeling in de graaf zit weet hij juist níét — hij heeft geen tools —
        en die vraag hoort dus naar de antwoord-worker, die zoekt en het zelf zegt als hij niets
        vindt. Anders wijst een gok een vraag af waar wel degelijk iets over te vinden was: "de
        milieuwet" leverde een afwijzing op terwijl art. 36 IW 1990 de Wet belastingen op
        milieugrondslag noemt.
        """
        writer = get_stream_writer()
        melding = (
            "Deze vraag gaat niet over Nederlandse wet- en regelgeving, dus daar kan ik je niet mee "
            "helpen. Vraag me gerust naar een bepaling, een begrip of de samenhang tussen artikelen "
            "— of laat me een artikel annoteren volgens het JAS."
        )
        writer({"type": "token", "content": melding})
        _stap(writer, "Klaar", "niet beantwoord — buiten de wetgeving")
        return {"answer": melding, "messages": [{"role": "assistant", "content": melding}]}

    def agent_node(state: State) -> dict[str, Any]:
        writer = get_stream_writer()
        # Alleen bij de eerste beurt: daarna is elke ronde al herkenbaar aan de graafbevragingen, en
        # zou dit bij elke tool-lus opnieuw voorbijkomen.
        if not state.get("turns"):
            spec_naam = state.get("specialist") or DEFAULT_SPECIALIST
            _stap(writer, f"Specialist {spec_naam}", "raadpleegt de kennisgraaf")
        # De annotatie-route draait de agent⇄tools-lus als OPHAAL-agent (retrieval-specialist): hij
        # vindt de exacte bepaling. De JAS-annotatie gebeurt daarna in annoteer_node (pure LLM-call).
        spec_naam = "retrieval" if state.get("specialist") == "annotatie" else state.get("specialist")
        spec = get_specialist(spec_naam)
        # Twee delen, en de volgorde is betekenisdragend: het stabiele deel (identiteit +
        # specialist) is bij elke tool-ronde van elke beurt hetzelfde en draagt daarom het
        # prompt-cache-punt; het plan, de geheugen-context en de adviescontext verschillen per
        # beurt en horen er dus áchter. Caching is een prefix-match — één byte verschil vóór het
        # cache-punt maakt de cache waardeloos.
        stabiel = SYSTEM_PROMPT + (f"\n\n{spec.system}" if spec.system else "")
        variabel = ""
        if state.get("plan"):
            variabel += f"AANPAK (door jou gepland):\n{state['plan']}"
        variabel += _memory_context(state)
        variabel += _advies_context(state)

        # De annotatie-worker produceert JSON, geen leesbaar antwoord — díe narratie tonen we niet
        # (annoteer_node emit straks een korte samenvatting). De narratie van een gewone worker is de
        # "denkproces"-stroom (reason), niet het antwoord: die scheiden we van het eindantwoord (token).
        stream_naar_denk = state.get("specialist") != "annotatie"
        with llm.stream(
            # Deze node draait twee verschillende rollen: de OPHAAL-agent (annotatieroute — zoeken
            # en ophalen) en de QA-specialisten (die het antwoord zelf schrijven). Alleen de eerste
            # heeft een eigen modelknop.
            model=model_ophaal if spec_naam == "retrieval" else model,
            max_tokens=4096,
            system=[stabiel, variabel],
            tools=anthropic_schemas(only=spec.tools),
            # Historie begrenzen (tegen onbegrensde promptgroei in een lange sessie); state blijft heel.
            messages=_trim_messages(_schoon_messages(state["messages"]), settings.max_history_chars),
        ) as stream:
            # Beurt-narratie stroomt per beurt binnen als `reason` (het denkproces). Op een beurt-grens
            # ontbreekt anders een scheiding, zodat "…tegelijkertijd." + "De thesaurus…" aan elkaar
            # plakt. Emit één alinea-scheiding vóór de éérste tekst van een vervolgbeurt (turns>0).
            # Lazy, zodat een tool-only beurt (geen tekst) geen loshangende of dubbele witregel geeft.
            first_delta = True
            for delta in stream.text_deltas:
                if stream_naar_denk:
                    if first_delta and state.get("turns", 0) > 0:
                        writer({"type": "reason", "content": "\n\n"})
                    writer({"type": "reason", "content": delta})
                first_delta = False
            final = stream.final_message()

        tool_uses, text_parts = _parse_final(final)

        # max_turns-vangnet: op de laatste toegestane beurt geen openstaande tool_use persisteren.
        # Anders belandt er een assistant(tool_use) zónder tool_result in de checkpointer (orphan →
        # de volgende beurt in dezelfde conversatie crasht op Anthropic 400) én blijft het antwoord
        # leeg. Laat de tools dan vallen en lever een net eind-antwoord (desnoods een korte melding).
        if tool_uses and state.get("turns", 0) + 1 >= settings.max_turns:
            tool_uses = []
            if not any(p and p.strip() for p in text_parts):
                text_parts = [
                    "Ik kon deze vraag niet binnen de beurtlimiet afronden; stel 'm eventueel gerichter."
                ]

        assistant_content: list[dict[str, Any]] = [{"type": "text", "text": p} for p in text_parts if p and p.strip()]
        assistant_content += [
            {"type": "tool_use", "id": t["id"], "name": t["name"], "input": t["input"]}
            for t in tool_uses
        ]

        upd: dict[str, Any] = {
            "messages": [{"role": "assistant", "content": assistant_content}],  # delta (append-reducer)
            "pending_tools": tool_uses,
            "turns": state.get("turns", 0) + 1,
        }
        if not tool_uses:
            # De tool-loze beurt is het eindantwoord: dát is de leesbare `token`-stroom (de annotatie-
            # route levert JSON, geen antwoord — daar geen token; annoteer_node vat samen).
            antwoord = "\n\n".join(p for p in text_parts if p)
            upd["answer"] = antwoord
            if stream_naar_denk and antwoord:
                writer({"type": "token", "content": antwoord})
        return upd

    def route_after_agent(state: State) -> str:
        if state.get("pending_tools") and state.get("turns", 0) < settings.max_turns:
            return "tools"
        if state.get("specialist") == "annotatie":
            return "annoteer"  # ophaal-agent klaar → de aparte annoteer-stap
        return "verify"

    def annoteer_node(state: State) -> dict[str, Any]:
        """Aparte annoteer-stap: de ophaal-agent heeft de bepaling opgehaald (in de source_trace).
        Hier doet een PURE LLM-call (geen tools) de JAS-analyse op ALLEEN die tekst en gronden we elk
        element ertegen. De gegronde voorstellen gaan naar de state; de aparte critic_node scoort ze en
        emit ze dán als `element`-events. annoteer emit alléén `doel` (en een melding bij lege uitkomst)."""
        writer = get_stream_writer()

        # Een ONDERWERP in plaats van een bepaling: de ophaal-agent legt kandidaten voor en wij
        # annoteren nog niets. Welke bepaling de werkvoorraad in gaat is een inhoudelijke keuze van
        # de jurist, niet iets om te laten raden door een semantische zoekopdracht.
        kandidaten = _kandidaten_uit_json(state.get("answer", ""))
        if kandidaten:
            writer({"type": "kandidaten", "kandidaten": kandidaten})
            melding = (
                f"Ik vond {len(kandidaten)} bepalingen over dit onderwerp. Kies welke je wilt laten "
                "annoteren."
            )
            writer({"type": "token", "content": melding})
            return {"answer": melding, "voorstellen": [],
                    "messages": [{"role": "assistant", "content": melding}]}

        doel = _bepaal_doel(state)
        # Gericht ophalen op basis van het doel — niet reconstrueren uit de trace. Zie
        # `_corpus_voor_doel`: die reconstructie mengt bepalingen en is afgekapt op 8000 tekens.
        corpus = _corpus_voor_doel(doel, graph, state.get("source_trace", []))
        aanduiding = doel.get("artikel") or doel.get("nummer") or ""

        if not corpus.strip():
            melding = (
                "Ik kon de gevraagde bepaling niet ophalen om te annoteren — controleer de wet en het "
                "artikel/lid (bij een beleidsregel bv. '9.1')."
            )
            writer({"type": "token", "content": melding})
            return {"answer": melding, "voorstellen": [], "messages": [{"role": "assistant", "content": melding}]}

        plek = f"art. {aanduiding}" + (f" lid {doel['lid']}" if doel.get("lid") else "")
        _stap(writer, "Annoteerder", f"leest {plek} ({len(corpus)} tekens)")

        resp = llm.create(
            model=model,
            max_tokens=8192,
            system=annotatie_systeemprompt(),
            tools=[],
            messages=[{"role": "user", "content": annotatie_userprompt(doel.get("bwbId", ""), aanduiding, corpus, doel.get("lid", ""))}],
        )
        llm_text = "".join(b.text for b in resp.content if b.type == "text")
        # Bewust zónder `geldige_ids`: in de eerste ronde is er binnen deze beurt nog geen element om
        # te overschrijven, dus een id uit het model is hooguit een raar id. De strengheid hoort in
        # de herziening, waar een verwisseld id wél een bestaande markering raakt.
        voorstellen, verworpen = _verwerk(
            llm_text, corpus, doel.get("bwbId", ""), aanduiding, doel.get("lid", ""),
        )
        _stap(writer, "Annoteerder", _annoteer_melding(voorstellen, verworpen))

        # Stuur de opgehaalde tekst mee zodat de frontend precies dít toont (één bron, ook voor divisies).
        doel_uit = {**doel, "leden_teksten": [{"lid": doel.get("lid", ""), "tekst": corpus}]}
        writer({"type": "doel", "doel": doel_uit})
        if not voorstellen:
            leeg = f"Ik vond geen JAS-elementen om te markeren in artikel {aanduiding}" + (
                f" lid {doel['lid']}." if doel.get("lid") else "."
            )
            writer({"type": "token", "content": leeg})
            return {"answer": leeg, "voorstellen": [], "verworpen_fragmenten": [], "corpus": corpus,
                    "messages": [{"role": "assistant", "content": leeg}]}
        # Markeringen die de JURIST zelf maakte gaan mee als BEVROREN voorstellen: de Critic mag er
        # iets van vinden (dat is een tweede paar ogen op eigen werk), maar ze doen niet mee in de
        # herzieningslus en worden nooit gewijzigd. De api weigert dat trouwens ook.
        # Ze moeten wél over DEZE bepaling gaan: een fragment dat niet letterlijk in het opgehaalde
        # corpus staat, kan de Critic niet beoordelen. Zonder deze grens oordeelt hij over een
        # markering uit een ander artikel die de werkplek meestuurde — en dat leest als een
        # kanttekening op werk dat hier niet ligt.
        meegestuurd = [
            e for e in ((state.get("context") or {}).get("bestaande_elementen") or [])
            if e.get("herkomst") == "mens" and e.get("tekst")
        ]
        eigen = [
            {
                "id": e.get("id", ""), "klasse": e.get("klasse", ""), "tekst": e.get("tekst", ""),
                "lid": e.get("lid", ""), "toelichting": "", "alternatieven": [],
                "grounded": True, "vindplaats": "", "aandacht": "", "critic": "",
                "van_jurist": True,
            }
            for e in meegestuurd
            if komt_letterlijk_voor(corpus, str(e.get("tekst", "")))
        ]
        if len(eigen) < len(meegestuurd):
            logger.info(
                "eigen markeringen buiten deze bepaling overgeslagen",
                extra={"meegestuurd": len(meegestuurd), "beoordeeld": len(eigen)},
            )

        # De verworpen fragmenten gaan mee de state in: de herzieningsronde (zie `route_na_critic`)
        # kan het model daarmee zijn eigen bijna-goede citaten laten repareren.
        return {
            "voorstellen": [v.model_dump() for v in voorstellen] + eigen,
            "verworpen_fragmenten": [x.model_dump() for x in verworpen],
            # De Critic en de herziening lezen dit; zonder dit zouden ze de bepaling opnieuw ophalen
            # (of erger: terugvallen op de trace en over een ándere tekst oordelen).
            "corpus": corpus,
            "answer": "",
        }

    def critic_node(state: State) -> dict[str, Any]:
        """Critic-pas: beoordeelt de gegronde voorstellen en zet per element een aandacht-niveau
        (groen/geel/rood) + motivatie, plus een lijst waarschijnlijk ontbrekende elementen. Eén
        LLM-call (geen tools).

        Emit BEWUST NIETS: dat doet `emit_node`, na de laatste ronde. Zou deze node al `element`-events
        sturen, dan zag de werkplek elke tussenversie van de herzieningslus voorbijkomen.

        Faalt de Critic → `critic_gefaald`, elementen komen door met lege aandacht en de lus wordt
        overgeslagen (nooit de annotatie breken)."""
        writer = get_stream_writer()
        voorstellen = list(state.get("voorstellen") or [])
        if not voorstellen:
            return {}  # annoteer_node heeft de lege/foutmelding al geëmit

        _stap(writer, "Critic", f"beoordeelt {len(voorstellen)} markeringen")
        corpus = _corpus(state)

        oordelen: dict[str, Any] = {}
        ontbrekend: list[Any] = []
        gefaald = False
        try:
            resp = llm.create(
                model=model,
                max_tokens=2048,
                system=critic_systeemprompt(),
                tools=[],
                messages=[{"role": "user", "content": critic_userprompt(
                    voorstellen, corpus, list(state.get("gemeld_ontbrekend") or []),
                )}],
            )
            crit_text = "".join(b.text for b in resp.content if b.type == "text")
            oordelen, ontbrekend = _verwerk_critic(crit_text, [str(v.get("id", "")) for v in voorstellen])
        except Exception:  # noqa: BLE001 — Critic mag de annotatie nooit breken
            gefaald = True
            logger.warning("critic: beoordeling mislukt; elementen zonder aandacht doorgelaten", exc_info=True)

        if gefaald:
            _stap(writer, "Critic", "overgeslagen (fout) — de voorstellen blijven staan")
            # Laat de voorstellen ONGEMOEID. In een tweede ronde staat er al een oordeel van de
            # eerste pas op; dat overschrijven met lege waarden zou een geslaagde beoordeling
            # ongedaan maken omdat een latere poging mislukte.
            return {
                "voorstellen": voorstellen,
                "critic_feedback": [],
                "critic_gefaald": True,
            }

        # Rondenummer voor het spoor: 1 = het eerste oordeel, 2 = de eindbeoordeling na correctie.
        ronde = int(state.get("critic_ronde") or 0) + 1

        feedback: list[dict[str, Any]] = []
        for v in voorstellen:
            oordeel = oordelen.get(str(v.get("id", "")))
            aandacht = oordeel.aandacht if oordeel else ""
            # De motivatie gaat één-op-één naar de reviewkaart. Interne ids horen daar niet: de
            # Critic gebruikt ze om naar buurelementen te verwijzen, de jurist leest een hexcode.
            motivatie = vervang_ids_door_citaat(oordeel.motivatie, voorstellen) if oordeel else ""
            # Alternatieven forceren GEEN geel meer. Dat maakte disambiguatie ononderscheidbaar van
            # een probleem: een element met alternatieven kon nooit groen worden, dus stond straks
            # alles "met aandacht" en zei die vlag niets meer. Twijfel telt nu apart (zie emit_node).
            v["aandacht"] = aandacht
            v["critic"] = motivatie
            if oordeel is not None:
                feedback.append({"id": v.get("id", ""), **oordeel.model_dump()})
                # Het spoor per element: hierop leunt de volgende Critic-pas (geheugen), de kaart in
                # de werkplek (het heen-en-weer) en de merge in de api (die matcht op rondenummer).
                v.setdefault("critic_rondes", []).append({
                    "ronde": ronde,
                    "aandacht": aandacht,
                    "motivatie": motivatie,
                    "actie": oordeel.actie,
                    # Expliciet, ook al is False de default in het contract: de patcher zet dit
                    # verderop op True, en een spoor dat het veld pas krijgt zódra er iets gebeurde
                    # is moeilijker te lezen dan een spoor dat het altijd draagt.
                    "toegepast": False,
                    "voorstel_klasse": oordeel.voorstel_klasse,
                    "voorstel_tekst": oordeel.voorstel_tekst,
                })

        al_gemeld = set(state.get("gemeld_ontbrekend") or [])
        huidig = {_ontbrekend_sleutel(o.model_dump()) for o in ontbrekend}
        nieuw_ontbrekend = [o.model_dump() for o in ontbrekend
                            if _ontbrekend_sleutel(o.model_dump()) not in al_gemeld]

        # De eindbeoordeling gaat rechtstreeks naar de jurist; er komt geen patcher meer overheen
        # die haar kan wegen. Dus hier, en alleen hier, dempen we een oordeel dat de eigen
        # uitgevoerde correctie terugdraait — zie `demp_zelfweerspreking`.
        gedempt = demp_zelfweerspreking(voorstellen) if ronde >= 2 else 0

        _stap(writer, "Critic",
              _critic_melding(oordelen, ontbrekend, len(nieuw_ontbrekend), gedempt))

        # `voorstellen` expliciet teruggeven: eerder werkten de aandacht-velden alleen door omdat het
        # dezelfde dict-objecten waren. Dat is fragiel zodra er meerdere rondes over de state lopen.
        return {
            "voorstellen": voorstellen,
            "critic_feedback": feedback,
            "critic_ontbrekend": [o.model_dump() for o in ontbrekend],
            "critic_gefaald": gefaald,
            # De teller telt CRITIC-PASSEN (1 = eerste oordeel, 2 = eindbeoordeling na correctie) en
            # hoort daarom hier thuis. Hij zat in de herziener en telde daar pogingen — een teller die
            # ergens anders wordt opgehoogd dan waar hij over gaat.
            "critic_ronde": ronde,
            # Wat al ooit is gemeld start geen nieuwe ronde meer. Hier berekend en niet in de route:
            # daar is de accumulatie al bijgewerkt en zou álles als "al gemeld" gelden.
            "nieuw_ontbrekend": nieuw_ontbrekend,
            "gemeld_ontbrekend": sorted(al_gemeld | huidig),
        }

    def _open_werk(state: State) -> bool:
        """Ligt er werk dat alléén het model kan doen?

        Twee dingen, en ze hebben gemeen dat er brontekst voor gelezen moet worden in plaats van een
        instructie uitgevoerd: een gemeld ontbrekend element (waar staat het?) en een eerder verworpen
        fragment (welk citaat werd bedoeld?).

        Correctie-instructies staan hier NIET meer bij. `vervang` en `verwijder` waren de reden dat de
        herziener draaide, en die voert de patcher nu uit — exact, zonder call, zonder onderhandeling.

        Eén definitie, gebruikt door de routering én door de stopreden in `emit_node`. Stonden die los
        van elkaar, dan meldt de tijdlijn iets anders dan er gebeurde — en dat is precies het signaal
        waarmee je deze keten beoordeelt.
        """
        return bool(state.get("nieuw_ontbrekend")) or bool(state.get("verworpen_fragmenten"))

    def route_na_critic(state: State) -> str:
        """Naar de correctiestap, of naar de jurist?

        De keten is lineair: `critic₁ → patch → [herzie] → [critic₂] → emit`. Er valt hier dus niets
        te kiezen behalve of er nog een correctieronde ís — en of dit al de eindbeoordeling was.
        Eerder zat hier de ingang van een cyclus (`critic ⇄ herzie`) met vier guards eromheen.
        """
        if settings.critic_max_rondes <= 0:
            return "emit"                                   # correctie uit: exact het oude gedrag
        if state.get("critic_gefaald"):
            return "emit"                                   # nooit de annotatie breken
        if int(state.get("critic_ronde") or 0) >= 2:
            return "emit"                                   # dit wás de eindbeoordeling
        return "patch"

    def patch_node(state: State) -> dict[str, Any]:
        """Voer de correcties van de Critic uit — in code, niet via een tweede taalmodel.

        Zie `annotatie.pas_critic_toe` voor de regels en waarom ze zo liggen. Deze node kost niets:
        geen LLM-call, geen graafverkeer.
        """
        writer = get_stream_writer()
        voorstellen, telling, rest = pas_critic_toe(
            list(state.get("voorstellen") or []),
            list(state.get("critic_feedback") or []),
            _corpus(state),
        )
        if telling:
            delen = []
            if telling.toegepast:
                delen.append(f"{telling.toegepast} "
                             + ("aanwijzing" if telling.toegepast == 1 else "aanwijzingen") + " toegepast")
            if telling.alternatief:
                delen.append(f"{telling.alternatief} "
                             + ("twijfel" if telling.alternatief == 1 else "twijfels")
                             + " als alternatief doorgegeven")
            _stap(writer, "Correctie", ", ".join(delen))
        # Alleen een echte wijziging vraagt om een nieuw oordeel. Een alternatief laat het element
        # ongemoeid — daar geldt het oordeel van de eerste pas gewoon nog.
        #
        # `critic_feedback` wordt teruggebracht tot wat de patcher NIET heeft afgehandeld. Anders
        # krijgt de herziener dezelfde instructies opnieuw voorgelegd: de correcties die hier net
        # zijn uitgevoerd (dubbel werk) én de gele voorkeuren die hier bewust niet zijn uitgevoerd —
        # en dan voert een taalmodel alsnog uit wat juist aan de jurist zou worden voorgelegd.
        return {
            "voorstellen": voorstellen,
            "patch_toegepast": telling.toegepast,
            "critic_feedback": rest,
        }

    def route_na_patch(state: State) -> str:
        """Wat er ná het patchen nog over is.

        - **Restant voor het model**: een bijna-goed citaat repareren of een gemeld ontbrekend element
          toevoegen. Dat is brontekst lezen, geen instructie uitvoeren — dus daar draait de herziener.
        - **Alleen gepatcht**: dan volgt de eindbeoordeling, zodat het oordeel op de kaart gaat over
          de versie die de jurist vóór zich krijgt en niet over de versie die net is vervangen.
        - **Niets veranderd**: klaar. Dit is het normale geval en het kost geen enkele extra call.
        """
        if _open_werk(state):
            return "herzie"
        return "critic" if state.get("patch_toegepast") else "emit"

    def herzie_node(state: State) -> dict[str, Any]:
        """Laat de annoteerder de Critic-instructies verwerken. Eén LLM-call, geen tools.

        Conservatief samenvoegen: wat de herziening niet noemt blijft staan. Alleen een expliciete
        `verwijder`-instructie laat een element verdwijnen. Zo kan een doordrammende Critic geen goede
        elementen wegvagen, en levert een half-mislukte herziening nooit minder op dan we al hadden.
        """
        writer = get_stream_writer()
        alle = list(state.get("voorstellen") or [])
        # Markeringen van de jurist gaan de herziening NIET in: de agent herschrijft ze niet, ook niet
        # als de Critic er iets van vindt. Die bevinding komt terug als suggestie, niet als wijziging.
        van_jurist = [v for v in alle if v.get("van_jurist")]
        voorstellen = [v for v in alle if not v.get("van_jurist")]
        # De herziener draait hoogstens één keer en telt niets meer op: de keten is lineair, dus er
        # is geen ronde om te tellen. `critic_ronde` gaat over de Critic-passen en wordt daar gezet.
        ronde = int(state.get("critic_ronde") or 0)
        if not voorstellen:
            # Alleen markeringen van de jurist: er valt niets te herzien.
            return {"stop_reden": "niets te herzien"}
        doel = _bepaal_doel(state)
        corpus = _corpus(state)
        aanduiding = doel.get("artikel") or doel.get("nummer") or ""
        feedback = [f for f in (state.get("critic_feedback") or [])
                    if f.get("id") not in {v.get("id") for v in van_jurist}]

        try:
            resp = llm.create(
                model=model,
                max_tokens=8192,
                system=herziening_systeemprompt(),
                tools=[],
                messages=[{"role": "user", "content": herziening_userprompt(
                    voorstellen, feedback,
                    state.get("critic_ontbrekend") or [],
                    state.get("verworpen_fragmenten") or [],
                    corpus,
                )}],
            )
            llm_text = "".join(b.text for b in resp.content if b.type == "text")
            herzien, verworpen = _verwerk(
                llm_text, corpus, doel.get("bwbId", ""), aanduiding, doel.get("lid", ""),
                # Alleen de id's die de herziener zélf voorgelegd kreeg. Verwisselt het model er
                # twee, dan zou het anders element A overschrijven met de inhoud van B.
                geldige_ids={str(v.get("id", "")) for v in voorstellen if v.get("id")},
            )
        except Exception:  # noqa: BLE001 — een mislukte herziening mag de annotatie niet breken
            logger.warning("herziening: mislukt; vorige voorstellen behouden", exc_info=True)
            _stap(writer, f"Herziening {ronde}", "mislukt — vorige voorstellen behouden")
            return {"critic_feedback": [], "stop_reden": "herziening mislukt"}

        if not herzien:
            logger.warning("herziening: leverde niets gegronds op; vorige voorstellen behouden")
            _stap(writer, f"Herziening {ronde}",
                  "leverde niets gegronds op — vorige voorstellen behouden")
            return {"critic_feedback": [], "stop_reden": "geen wijziging meer"}

        te_verwijderen = {f.get("id") for f in feedback if f.get("actie") == "verwijder"}
        samengevoegd = {v["id"]: v for v in voorstellen if v.get("id") not in te_verwijderen}
        # Een herziening die een bestaand fragment opnieuw voorstelt ZONDER het id mee te sturen,
        # krijgt een vers id — en dan staat dezelfde markering er twee keer. Dat viel op dev op:
        # "bij zijn in functie treden" tweemaal als Rechtsfeit. Koppel daarom ook op de inhoud.
        # De sleutel telt de klasse NIET mee: een herclassificatie is precies wat een herziening
        # hoort te doen, en met de klasse erin werd zo'n herziening een tweede element naast het
        # origineel — dezelfde span, twee tegenstrijdige klassen op het reviewscherm.
        op_inhoud = {
            sleutel_van(v.get("tekst", ""), v.get("lid", "")): v["id"]
            for v in samengevoegd.values()
        }
        for nieuw_v in herzien:
            nieuw_dict = nieuw_v.model_dump()
            bestaand_id = op_inhoud.get(sleutel_van(nieuw_v.tekst, nieuw_v.lid))
            if bestaand_id and bestaand_id != nieuw_v.id:
                # Het OUDSTE id wint: daar hangen de beslissingen van de jurist en het auditspoor aan.
                nieuw_dict["id"] = bestaand_id
                nieuw_v = nieuw_v.model_copy(update={"id": bestaand_id})
            vorig = samengevoegd.get(nieuw_v.id)
            # De rondegeschiedenis gaat ALTIJD mee: die gaat over wat er gebeurd is, niet over de
            # huidige versie. Zonder dit begint de volgende Critic-pas weer met een schone lei —
            # precies de reden dat de lus nooit convergeerde.
            if vorig:
                nieuw_dict["critic_rondes"] = list(vorig.get("critic_rondes") or [])
                # Ook de alternatieven blijven: de patcher zet de twijfel van de Critic daar neer, en
                # het model levert bij een herziening zijn eigen lijstje op. Namen we alleen dat
                # laatste over, dan wiste een herziening precies de voorkeur die de jurist met één
                # klik had kunnen overnemen — op dev verdween "Parameter en parameterwaarde" zo uit
                # beeld. Samenvoegen op klasse, het bestaande eerst.
                bestaand = list(vorig.get("alternatieven") or [])
                gezien_alt = {str(a.get("klasse")) for a in bestaand}
                nieuw_dict["alternatieven"] = bestaand + [
                    a for a in (nieuw_dict.get("alternatieven") or [])
                    if str(a.get("klasse")) not in gezien_alt
                ]
            # Een herziening levert verse voorstellen zonder oordeel. Is het element inhoudelijk
            # ongewijzigd, dan geldt het vorige oordeel nog gewoon — dat weggooien zou een groen
            # vinkje laten verdwijnen omdat er elders in de tekst iets veranderde. Bij een écht
            # gewijzigd element hoort de aandacht leeg: die versie is nog niet beoordeeld.
            if vorig and all(vorig.get(k) == nieuw_dict.get(k) for k in ("klasse", "tekst", "lid")):
                nieuw_dict["aandacht"] = vorig.get("aandacht", "")
                nieuw_dict["critic"] = vorig.get("critic", "")
            samengevoegd[nieuw_v.id] = nieuw_dict

        uit = list(samengevoegd.values())
        _stap(writer, f"Herziening {ronde}", _herzien_melding(voorstellen, uit))

        # Wat is er écht veranderd? De eindbeoordeling leest dit ("je zei X, en de annotator heeft het
        # wel/niet gedaan"). De boekhouding van gemotiveerd genegeerde instructies is weg: die bestond
        # om een cyclus te laten stoppen die er niet meer is.
        voor_op_id = {v.get("id"): v for v in voorstellen}
        gewijzigd = {
            v.get("id") for v in uit
            if v.get("id") not in voor_op_id
            or any(voor_op_id[v["id"]].get(k) != v.get(k) for k in ("klasse", "tekst", "lid"))
        }
        for v in uit:
            v["aangepast_na_kritiek"] = v.get("id") in gewijzigd

        return {
            "voorstellen": uit + van_jurist,
            "verworpen_fragmenten": [x.model_dump() for x in verworpen],
            "critic_feedback": [],
            # Niets meer voor het model te doen: de herziener draait per beurt hoogstens één keer.
            "nieuw_ontbrekend": [],
            "verworpen_fragmenten": [x.model_dump() for x in verworpen] if gewijzigd else [],
        }

    # Er is geen `route_na_herziening` meer: de herziener gaat altijd door naar de eindbeoordeling
    # (`g.add_edge("herzie", "critic")`). Dat was de terugweg van een cyclus, met
    # `herziening_wijzigde` als rem — en die cyclus bestaat niet meer.

    def emit_node(state: State) -> dict[str, Any]:
        """De enige plek die annotatie-events uitstuurt: één `run`, `element` per voorstel, één
        `ontbrekend`, en de samenvattings-`token`. Apart gehouden van de Critic zodat de
        herzieningslus zoveel rondes kan draaien als nodig zonder dat de werkplek tussenversies
        te zien krijgt."""
        writer = get_stream_writer()
        voorstellen = list(state.get("voorstellen") or [])
        if not voorstellen:
            return {}
        doel = _bepaal_doel(state)
        aanduiding = doel.get("artikel") or doel.get("nummer") or ""
        ontbrekend = state.get("critic_ontbrekend") or []
        corpus = _corpus(state)

        # Vóór de elementen: met welk model deze voorstellen zijn gemaakt. Zonder dit is achteraf
        # niet meer vast te stellen wat een markering produceerde — de werkplek legt het vast bij
        # de api en de export draagt het als herkomst.
        writer({"type": "run", "run": AgentRun(
            model=model,
            provider=settings.llm_provider,
            agent_versie=settings.agent_versie,
            critic_rondes=int(state.get("critic_ronde") or 0),
            stop_reden=str(state.get("stop_reden") or ""),
            tijd=datetime.now(timezone.utc),
        ).model_dump(mode="json")})

        met_aandacht = 0
        met_twijfel = 0
        for v in voorstellen:
            if v.get("van_jurist"):
                # Geen `element`-event: dit element bestaat al in het document en mag niet opnieuw
                # als voorstel binnenkomen. Alleen het oordeel gaat mee, als suggestie.
                if v.get("aandacht"):
                    writer({"type": "suggestie", "suggestie": {
                        "element_id": v.get("id", ""), "aandacht": v.get("aandacht", ""),
                        "motivatie": v.get("critic", ""),
                    }})
                continue
            if v.get("aandacht") in ("geel", "rood"):
                met_aandacht += 1
            elif v.get("alternatieven"):
                # Twijfel, geen bezwaar: de annoteerder zag twee plausibele klassen. Apart tellen,
                # anders verdrinkt een écht aandachtspunt tussen de disambiguaties.
                met_twijfel += 1
            writer({"type": "element", "element": v})

            # Een voorstel uit de EINDbeoordeling komt door geen enkele stap meer heen — de patcher
            # draaide al. Als suggestie ernaast leggen kan wel: dan neemt de jurist het over met één
            # klik, en landt het als zíjn beslissing in het spoor.
            klasse, tekst, waarom = openstaand_voorstel(v, corpus)
            if klasse or tekst:
                writer({"type": "suggestie", "suggestie": {
                    "element_id": v.get("id", ""), "aandacht": v.get("aandacht", ""),
                    "motivatie": waarom, "voorstel_klasse": klasse, "voorstel_tekst": tekst,
                }})
        writer({"type": "ontbrekend", "items": ontbrekend})

        eigen = [v for v in voorstellen if v.get("van_jurist")]
        voorstellen = [v for v in voorstellen if not v.get("van_jurist")]
        plek = f"artikel {aanduiding}" + (f" lid {doel['lid']}" if doel.get("lid") else "")
        delen = [f"Ik heb {len(voorstellen)} JAS-elementen voorgesteld voor {plek}"]
        if met_aandacht:
            delen.append(f"{met_aandacht} met aandacht")
        if met_twijfel:
            delen.append(f"{met_twijfel} met twijfel")
        if ontbrekend:
            delen.append(f"{len(ontbrekend)} mogelijk ontbrekend")
        met_suggestie = sum(1 for v in eigen if v.get("aandacht") in ("geel", "rood"))
        if met_suggestie:
            delen.append(f"{met_suggestie} kanttekening bij je eigen markeringen")
        if int(state.get("patch_toegepast") or 0):
            delen.append("na correctie door de Critic")
        samenvatting = "; ".join(delen) + "."
        # De stopreden hoort hier te worden afgeleid: `route_na_critic` weet hem wel, maar een
        # conditionele edge geeft alleen een naam terug en kan geen state schrijven. Alle feiten
        # staan hier, dus is dit de plek waar één waarheid overblijft.
        # Er is geen rondelimiet meer om te bereiken: de keten is lineair. Wat overblijft is of de
        # correctie überhaupt aanstond, of de Critic uitviel, en anders gewoon: klaar.
        reden = state.get("stop_reden") or (
            "Critic uitgevallen" if state.get("critic_gefaald")
            else "correctieronde uit" if settings.critic_max_rondes <= 0
            else "geen open punten"
        )
        _stap(writer, "Klaar", f"{reden} · {len(voorstellen)} elementen ter beoordeling")
        writer({"type": "token", "content": samenvatting})

        # Geheugen: leg een leesbaar spoor van de annotatie vast (met de elementen) zodat een
        # vervolgvraag ("waarom Rechtssubject?") context heeft.
        elems = "; ".join(f"{v.get('klasse', '')}: '{truncate(str(v.get('tekst', '')), 80)}'" for v in voorstellen[:12])
        geheugen = f"[Annotatie {plek}] Ik markeerde {len(voorstellen)} JAS-elementen: {elems}" + (
            " (…)" if len(voorstellen) > 12 else "."
        )
        return {"answer": samenvatting, "messages": [{"role": "assistant", "content": geheugen}]}

    def tools_node(state: State) -> dict[str, Any]:
        writer = get_stream_writer()
        pending = state.get("pending_tools", [])
        _stap(writer, "Graaf bevragen", ", ".join(_toolregel(t) for t in pending))
        trace = list(state.get("source_trace", []))
        results = []
        for tu in pending:
            result_text = truncate(dispatch(tu["name"], graph, tu["input"], settings))
            trace.append((tu["name"], result_text))
            results.append({"type": "tool_result", "tool_use_id": tu["id"], "content": result_text})
        return {
            "messages": [{"role": "user", "content": results}],  # delta
            "source_trace": trace,
            "pending_tools": [],
        }

    def verify_node(state: State) -> dict[str, Any]:
        writer = get_stream_writer()
        report = check_grounding(state.get("answer", ""), state.get("source_trace", []))
        # Deze controle heeft geen eigen narratie (geen LLM), dus zonder deze regel gebeurt er iets
        # wezenlijks — de brongetrouwheidstoets — zonder dat de jurist het ziet. De tijdlijn wordt
        # bij de beurt bewaard, dus dit is tegelijk het spoor waarop je achteraf terugvalt.
        _stap(writer, "Controle", _grounding_melding(report))
        return {
            "grounded": report.grounded,
            "cited": len(report.cited),
            "unsupported": report.unsupported,
            "niet_letterlijk": report.niet_letterlijk,
            "grounding_niveau": report.niveau,
        }

    def route_after_verify(state: State) -> str:
        if not state.get("grounded", True) and settings.grounding_correct and not state.get("corrected"):
            return "correct"
        return "finalize"

    def correct_node(state: State) -> dict[str, Any]:
        """Eén herkansing op wat de groundingcontrole afkeurde.

        De controle keurt twee dingen af en die vragen een ándere correctie. Deze node zag alleen
        `unsupported` (verzonnen vindplaatsen) en zweeg over `niet_letterlijk` (tekst die als citaat
        is gepresenteerd maar niet letterlijk in de bron staat). Bij een antwoord dat alléén op dat
        tweede struikelde — precies wat op dev gebeurde, zeven keer in één antwoord — ging er dus een
        volledige extra LLM-call de deur uit met de instructie "je noemde verwijzing(en) `` die niet
        uit de graaf kwamen": een lege opsomming en een verwijt dat niet klopte.
        """
        writer = get_stream_writer()
        unsupported = state.get("unsupported") or []
        niet_letterlijk = state.get("niet_letterlijk") or []

        opdrachten: list[str] = []
        if unsupported:
            opdrachten.append(
                f"Je noemde verwijzing(en) {', '.join(unsupported)} die niet uit de graaf-resultaten "
                "kwamen. Onderbouw ze met de tools of verwijder ze."
            )
        if niet_letterlijk:
            # Het fragment zelf mee, afgekapt: zonder de tekst weet het model niet wélk citaat het
            # moet herstellen, en met zeven lange passages loopt de prompt onnodig vol.
            passages = "; ".join(f'"{c[:120]}…"' if len(c) > 120 else f'"{c}"' for c in niet_letterlijk)
            opdrachten.append(
                f"Deze passages staan tussen aanhalingstekens maar niet letterlijk in de opgehaalde "
                f"tekst: {passages}. Herstel ze woord voor woord zoals ze in de bron staan, of haal "
                "de aanhalingstekens weg en geef het in je eigen woorden weer. Weglatingen met (...), "
                "eigen samenvattingen tussen [ ] en vet of cursief binnen een citaat maken het een "
                "parafrase — die presenteer je niet als citaat."
            )

        wat = " en ".join(
            deel for deel in (
                "niet-onderbouwde verwijzingen" if unsupported else "",
                "citaten die niet letterlijk zijn" if niet_letterlijk else "",
            ) if deel
        )
        _stap(writer, "Correctie", f"antwoord bijstellen op {wat}")
        return {
            "messages": [{"role": "user", "content": "Let op: " + " ".join(opdrachten)}],
            "corrected": True,
            "answer": "",
        }

    def finalize_node(state: State) -> dict[str, Any]:
        writer = get_stream_writer()

        # Vangnet tegen een stil leeg antwoord. Dat kan gebeuren als de agent een lege tekstbeurt
        # levert, of nadat correct_node het antwoord heeft gewist voor een grounding-correctie die
        # daarna niets oplevert. De gebruiker zag dan alleen de bronnen en de frontend-fallback
        # "(geen antwoord)" — zonder spoor in de logs. Liever een eerlijke melding, en altijd een
        # logregel zodat het volgende geval terug te vinden is.
        antwoord = state.get("answer", "") or ""
        if not antwoord.strip():
            reden = "grounding-correctie leverde geen antwoord" if state.get("corrected") else "lege antwoordbeurt"
            logger.warning(
                "leeg antwoord in finalize",
                extra={
                    "reden": reden,
                    "turns": state.get("turns", 0),
                    "specialist": state.get("specialist"),
                    "grounded": state.get("grounded", True),
                    "unsupported": state.get("unsupported", []),
                    "bronnen": len(state.get("source_trace", []) or []),
                },
            )
            antwoord = (
                "Ik kon op basis van de geraadpleegde bronnen geen antwoord formuleren. "
                "De gevonden bronnen staan hieronder; stel de vraag eventueel gerichter "
                "(bijvoorbeeld met een specifiek artikel of lid)."
            )
            writer({"type": "token", "content": antwoord})
            state = {**state, "answer": antwoord}

        sources = collect_sources(state.get("source_trace", []))
        if settings.curate_sources:
            sources = curate_sources(sources, state.get("answer", ""))
        src_dicts = [s.model_dump() for s in sources]
        _stap(writer, "Klaar", f"{len(src_dicts)} bron" + ("nen" if len(src_dicts) != 1 else ""))
        writer({"type": "sources", "sources": src_dicts})
        writer({
            "type": "grounding",
            "grounded": state.get("grounded", True),
            "cited": state.get("cited", 0),
            "unsupported": state.get("unsupported", []),
            "niet_letterlijk": state.get("niet_letterlijk", []),
            "niveau": state.get("grounding_niveau", "gegrond"),
        })
        # entiteit-tier: alleen nieuwe IRI's toevoegen (append-reducer + dedup).
        existing = set(state.get("entities_seen") or [])
        new = [s["uri"] for s in src_dicts if s["uri"] not in existing]
        upd: dict[str, Any] = {"sources": src_dicts, "entities_seen": new}
        # In de decompositie-stroom stroomt het eind-antwoord uit synthesize_node en is het nog niet
        # in het durabele messages-kanaal beland (agent_node doet dat in de één-loop-stroom). Voeg het
        # hier één keer toe zodat het gespreksgeheugen het antwoord onthoudt.
        if settings.enable_decomposition:
            upd["messages"] = [
                {"role": "assistant", "content": [{"type": "text", "text": state.get("answer", "")}]}
            ]
        return upd

    # ---- Decompositie-nodes (multi-hop; alleen actief bij enable_decomposition) --------------------

    def decompose_node(state: State) -> dict[str, Any]:
        """Splits de vraag in geordende deelvragen (één LLM-call). Enkelvoudig → één deelvraag."""
        writer = get_stream_writer()
        resp = llm.create(
            model=model,
            max_tokens=400,
            system=_DECOMPOSE_SYSTEM + _memory_context(state),
            tools=[],
            messages=[{"role": "user", "content": state["question"]}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        subs: list[str] = []
        for line in text.splitlines():
            m = re.match(r"^\s*\d+[.)]\s*(.+)$", line)
            if m:
                subs.append(m.group(1).strip())
        if not subs:
            subs = [state["question"]]
        subs = subs[: settings.max_subquestions]
        if len(subs) > 1:
            _stap(writer, "Decompositie", f"{len(subs)} deelvragen")
        return {"sub_questions": subs}

    def solve_node(state: State) -> dict[str, Any]:
        """Beantwoord elke deelvraag met een eigen agent⇄tools-loop (lokale scratch-messages).

        De per-beurt narratie stroomt als `reason` (het denkproces), nooit als `token`. Bij ÉÉN
        deelvraag (een simpele vraag) is er geen aparte synthese nodig: de tool-loze eindbeurt ís het
        eindantwoord en wordt als één `token` geëmit (en `answer` gezet), zodat een eenvoudige vraag
        geen synthese-tax betaalt. Bij MEERDERE deelvragen emit solve géén token — `synthesize_node`
        streamt dan het eindantwoord. De gedeelde source_trace accumuleert over álle deelvragen zodat
        grounding/provenance ongewijzigd werken.
        """
        writer = get_stream_writer()
        spec = get_specialist(state.get("specialist"))
        subs = state.get("sub_questions") or [state["question"]]
        enkelvoudig = len(subs) == 1  # simpele vraag: eindantwoord hier, synthese overslaan
        base_system = SYSTEM_PROMPT + (f"\n\n{spec.system}" if spec.system else "")
        schemas = anthropic_schemas(only=spec.tools)
        trace = list(state.get("source_trace", []))
        findings: list[dict[str, str]] = []
        for i, sub in enumerate(subs, 1):
            if len(subs) > 1:
                _stap(writer, f"Deelvraag {i}/{len(subs)}", sub[:80])
            # Zelfde splitsing als in `agent_node`: base_system is stabiel over alle deelvragen
            # heen, de bevindingen en de geheugen-context groeien per deelvraag.
            variabel = ""
            if findings:
                ctx = "\n".join(f"- {f['vraag']} → {f['antwoord'][:300]}" for f in findings)
                variabel += (
                    "EERDERE DEELBEVINDINGEN (context; verifieer elk feit opnieuw via de tools):\n" + ctx
                )
            variabel += _memory_context(state)
            msgs: list[dict[str, Any]] = [{"role": "user", "content": sub}]
            antwoord = ""
            for _turn in range(settings.sub_max_turns):
                # Op de laatste toegestane beurt bieden we géén tools meer aan. Zonder dat kon het
                # model blijven zoeken tot de lus afliep, waarna `antwoord` leeg bleef en de
                # gebruiker alleen bronnen zag: de vraag werd midden in de zoektocht afgekapt. Nu is
                # de laatste beurt gedwongen een antwoord op wat er is opgehaald.
                laatste_beurt = _turn == settings.sub_max_turns - 1
                if laatste_beurt:
                    _stap(writer, "Deelvraag", "beurtlimiet bereikt — verder met wat is gevonden")
                with llm.stream(
                    model=model, max_tokens=4096, system=[base_system, variabel],
                    tools=[] if laatste_beurt else schemas,
                    messages=_trim_messages(_schoon_messages(msgs), settings.max_history_chars),
                ) as stream:
                    first = True
                    for delta in stream.text_deltas:
                        if first and _turn > 0:
                            writer({"type": "reason", "content": "\n\n"})  # alinea-scheiding tussen beurten
                        writer({"type": "reason", "content": delta})
                        first = False
                    final = stream.final_message()
                tool_uses, text_parts = _parse_final(final)
                assistant_content: list[dict[str, Any]] = [{"type": "text", "text": p} for p in text_parts if p and p.strip()]
                assistant_content += [
                    {"type": "tool_use", "id": t["id"], "name": t["name"], "input": t["input"]}
                    for t in tool_uses
                ]
                msgs.append({"role": "assistant", "content": assistant_content})
                if not tool_uses:
                    antwoord = "\n\n".join(p for p in text_parts if p)
                    break
                _stap(writer, "Graaf bevragen", ", ".join(_toolregel(t) for t in tool_uses))
                results = []
                for tu in tool_uses:
                    result_text = truncate(dispatch(tu["name"], graph, tu["input"], settings))
                    trace.append((tu["name"], result_text))
                    results.append({"type": "tool_result", "tool_use_id": tu["id"], "content": result_text})
                msgs.append({"role": "user", "content": results})
            if not antwoord.strip():
                # Zou na het tools-loze vangnet hierboven niet meer moeten voorkomen; als het tóch
                # gebeurt is dat een lege modelrespons en willen we het terugvinden.
                logger.warning(
                    "deelvraag zonder antwoord",
                    extra={"deelvraag": sub[:120], "beurten": settings.sub_max_turns,
                           "specialist": state.get("specialist"), "bronnen": len(trace)},
                )
            findings.append({"vraag": sub, "antwoord": antwoord})
        upd: dict[str, Any] = {"sub_findings": findings, "source_trace": trace}
        if enkelvoudig:
            # Simpele vraag: de tool-loze eindbeurt ís het eind-antwoord (geen synthese) → als token.
            antwoord = findings[0]["antwoord"] if findings else ""
            upd["answer"] = antwoord
            if antwoord:
                writer({"type": "token", "content": antwoord})
        return upd

    def route_after_solve(state: State) -> str:
        # Eén deelvraag → antwoord staat al (gestreamd in solve); sla de synthese over.
        return "verify" if len(state.get("sub_questions") or []) <= 1 else "synthesize"

    def synthesize_node(state: State) -> dict[str, Any]:
        """Stel het eind-antwoord samen uit de deelbevindingen (streamt de tokens)."""
        writer = get_stream_writer()
        findings = state.get("sub_findings") or []
        _stap(writer, "Synthese", f"antwoord uit {len(findings)} deelbevindingen")
        bevindingen = "\n\n".join(
            f"DEELVRAAG: {f['vraag']}\nBEVINDING: {f['antwoord']}" for f in findings
        )
        system = _SYNTHESE_SYSTEM
        if state.get("corrected") and state.get("unsupported"):
            system += (
                "\n\nVerwijder of onderbouw deze eerder niet-gegronde verwijzingen: "
                + ", ".join(state["unsupported"]) + "."
            )
        user = f"OORSPRONKELIJKE VRAAG:\n{state['question']}\n\nBEVINDINGEN PER DEELVRAAG:\n{bevindingen}"
        parts: list[str] = []
        with llm.stream(
            model=model, max_tokens=4096, system=system, tools=[],
            messages=[{"role": "user", "content": user}],
        ) as stream:
            for delta in stream.text_deltas:
                parts.append(delta)
                writer({"type": "token", "content": delta})
            stream.final_message()
        return {"answer": "".join(parts).strip()}

    def resynth_node(state: State) -> dict[str, Any]:
        """Ongegronde synthese → markeer voor één her-synthese (synthesize_node leest corrected)."""
        return {"corrected": True, "answer": ""}

    g = StateGraph(State)

    def stopbaar(fn):
        """Elke node begint met de vraag of er nog gewerkt moet worden.

        Zo stopt een beurt op een **nodegrens** in plaats van halverwege een LLM-call: de state die
        al gecommit is blijft consistent, en de MCP-verbinding wordt netjes afgesloten. De prijs is
        dat stoppen tijd kost — de lopende stap maakt zichzelf af."""
        @functools.wraps(fn)
        def bewaakt(state: State) -> dict[str, Any]:
            if stop_check is not None and stop_check():
                raise BeurtGestopt()
            return fn(state)
        return bewaakt

    def add(naam: str, fn) -> None:
        """Registreer een node, altijd met de stopbewaking eromheen."""
        g.add_node(naam, stopbaar(fn))

    add("verify", verify_node)
    add("finalize", finalize_node)

    if settings.enable_decomposition:
        # Supervisor → (annotatie: agent⇄tools→annoteer_finalize | antwoord: decompose→solve→…→
        # finalize) → advance → (volgende worker | einde).
        add("supervisor", supervisor_node)
        add("decompose", decompose_node)
        add("solve", solve_node)
        add("synthesize", synthesize_node)
        add("resynth", resynth_node)
        add("agent", agent_node)
        add("tools", tools_node)
        add("annoteer", annoteer_node)
        add("critic", critic_node)
        add("patch", patch_node)
        add("herzie", herzie_node)
        add("emit", emit_node)
        add("advance", advance_node)
        add("afwijzen", afwijs_node)
        entrymap = {"agent": "agent", "annoteer": "annoteer", "decompose": "decompose",
                    "afwijzen": "afwijzen"}
        g.add_edge(START, "supervisor")
        g.add_edge("afwijzen", END)
        g.add_conditional_edges("supervisor", _entry_node, entrymap)
        g.add_edge("decompose", "solve")
        g.add_conditional_edges("solve", route_after_solve, {"verify": "verify", "synthesize": "synthesize"})
        g.add_edge("synthesize", "verify")
        g.add_conditional_edges("verify", route_after_verify, {"correct": "resynth", "finalize": "finalize"})
        g.add_edge("resynth", "synthesize")
        g.add_conditional_edges(
            "agent", route_after_agent,
            {"tools": "tools", "verify": "verify", "annoteer": "annoteer"},
        )
        g.add_edge("tools", "agent")
        g.add_edge("finalize", "advance")
        g.add_edge("annoteer", "critic")
        # De herzieningslus: de Critic wijst aan, de annoteerder herstelt, de Critic kijkt opnieuw.
        # `emit` is de enige uitgang, zodat de werkplek nooit tussenversies ziet.
        # Lineair: critic₁ → patch → [herzie] → [critic₂] → emit. Geen enkele edge wijst terug naar
        # een eerdere stap, dus er is geen cyclus meer om te laten convergeren.
        g.add_conditional_edges("critic", route_na_critic, {"patch": "patch", "emit": "emit"})
        g.add_conditional_edges("patch", route_na_patch,
                                {"herzie": "herzie", "critic": "critic", "emit": "emit"})
        g.add_edge("herzie", "critic")
        g.add_edge("emit", "advance")
        g.add_conditional_edges("advance", route_after_advance, {**entrymap, "einde": END})
        return g

    # Één-loop-stroom.
    add("agent", agent_node)
    add("tools", tools_node)
    add("correct", correct_node)

    if settings.enable_planning:
        # Supervisor → agent⇄tools → (verify→finalize | annoteer_finalize) → advance → (volgende | einde).
        add("supervisor", supervisor_node)
        add("annoteer", annoteer_node)
        add("critic", critic_node)
        add("patch", patch_node)
        add("herzie", herzie_node)
        add("emit", emit_node)
        add("advance", advance_node)
        add("afwijzen", afwijs_node)
        g.add_edge(START, "supervisor")
        g.add_conditional_edges("supervisor", _entry_node,
                                {"agent": "agent", "annoteer": "annoteer", "afwijzen": "afwijzen"})
        g.add_edge("afwijzen", END)
        g.add_conditional_edges(
            "agent", route_after_agent,
            {"tools": "tools", "verify": "verify", "annoteer": "annoteer"},
        )
        g.add_edge("tools", "agent")
        g.add_conditional_edges("verify", route_after_verify, {"correct": "correct", "finalize": "finalize"})
        g.add_edge("correct", "agent")
        g.add_edge("finalize", "advance")
        g.add_edge("annoteer", "critic")
        # De herzieningslus: de Critic wijst aan, de annoteerder herstelt, de Critic kijkt opnieuw.
        # `emit` is de enige uitgang, zodat de werkplek nooit tussenversies ziet.
        # Lineair: critic₁ → patch → [herzie] → [critic₂] → emit. Geen enkele edge wijst terug naar
        # een eerdere stap, dus er is geen cyclus meer om te laten convergeren.
        g.add_conditional_edges("critic", route_na_critic, {"patch": "patch", "emit": "emit"})
        g.add_conditional_edges("patch", route_na_patch,
                                {"herzie": "herzie", "critic": "critic", "emit": "emit"})
        g.add_edge("herzie", "critic")
        g.add_edge("emit", "advance")
        g.add_conditional_edges("advance", route_after_advance,
                                {"agent": "agent", "annoteer": "annoteer",
                                 "afwijzen": "afwijzen", "einde": END})
        return g

    # Geen classificatie (planning off, decomp off): pure QA-agent, ongewijzigd (geen annotatie-route).
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route_after_agent, {"tools": "tools", "verify": "verify"})
    g.add_edge("tools", "agent")
    g.add_conditional_edges("verify", route_after_verify, {"correct": "correct", "finalize": "finalize"})
    g.add_edge("correct", "agent")
    g.add_edge("finalize", END)
    return g
