"""
Het run-register: een beurt is een object van de server, geen HTTP-request.

Waarom dit bestaat. De werkplek hing een lopende beurt aan de SSE-verbinding van één tabblad: van
gesprek wisselen, naar een andere pagina navigeren of herladen sloot die verbinding en daarmee de
beurt. Het werk stopte daar niet eens van — de LangGraph-nodes zijn synchroon, dus een lopende
LLM-call draait door in de executor — het resultaat werd alleen weggegooid. We betaalden de rekening
en gooiden het antwoord weg.

Hier wordt dat omgedraaid, naar het model van Claude: de **run** draait als achtergrondtaak en houdt
zijn eigen event-log bij; een client *kijkt* mee en kan opnieuw aanhaken. Losraken is dus geen
annuleren — stoppen is een aparte, expliciete handeling (`vraag_stop`).

Aannames die je moet kennen voordat je dit uitbreidt:

- **Eén proces, één replica.** graph-qa draait als één uvicorn-proces zonder `--workers`; het
  register leeft in het geheugen. Komt er ooit een tweede replica, dan moet dit naar een gedeelde
  store — een aanhaker die op de verkeerde instantie landt vindt de run anders niet.
- **Een herstart wist het register.** Dat is bewust: hervatten-vanaf-checkpoint vraagt async nodes en
  een resume-pad dat de agent vandaag niet heeft. Een client die met een onbekend run_id terugkomt
  hoort te horen dát de run weg is, niet eeuwig te blijven wachten.
- **Alleen de run-taak schrijft.** Een abonnee die aanhaakt mag nooit een schrijfactie uitlokken;
  daarmee is aanhaken per definitie veilig en idempotent.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("graph_qa.runs")

# Hoeveel events er hoogstens in de log blijven staan. Ruim: een lange annotatiebeurt met veel
# narratie moet er integraal in passen.
MAX_EVENTS = 4000

# Hoe lang een afgeronde run nog opvraagbaar blijft. Lang genoeg dat je koffie kunt halen en de
# uitkomst alsnog ziet; kort genoeg dat het geheugen niet volloopt.
BEWAAR_NA_AFLOOP_S = 600.0

# Welke events bij het cappen mogen sneuvelen. Narratie is volume; betekenis is `doel`, `element`,
# `run`, `ontbrekend`, `sources`, `grounding`, `kandidaten`, `done` en `error` — die blijven staan,
# anders levert opnieuw aanhaken een verminkt resultaat op zonder dat iemand het merkt.
VLUCHTIGE_TYPES = frozenset({"token", "reason", "status"})


class RunBestaatAl(Exception):
    """Er loopt al een run voor dit gesprek. Draagt het actieve run_id, zodat de aanroeper kan
    aanhaken in plaats van een tweede run te starten.

    Dit is geen UI-nettigheid maar een gegevensbeschermer: `thread_id == conversation_id`, dus twee
    gelijktijdige lussen zouden door elkaar heen in dezelfde checkpointer-thread schrijven.
    """

    def __init__(self, run_id: str) -> None:
        super().__init__(f"Er loopt al een run voor dit gesprek: {run_id}")
        self.run_id = run_id


@dataclass
class Run:
    """Eén beurt, met alles wat een late kijker nodig heeft om hem te begrijpen."""

    run_id: str
    conversation_id: str
    # Namens wie deze beurt draait. Zonder dit is een run een capability: wie het id kent, leest mee
    # en kan hem stoppen. De rest van het platform scopet alles per gebruiker (404 op andermans
    # document); dat hoort hier niet anders te zijn.
    user_id: str = ""
    # De vraag hoort bij de run, niet bij het tabblad: wie halverwege aanhaakt moet de user-bubbel
    # erboven kunnen tonen in plaats van tokens uit het niets.
    vraag: str = ""
    status: str = "loopt"          # loopt | klaar | gestopt | mislukt
    # Elk event draagt zijn EIGEN `seq`, toegekend bij het toevoegen. Eerder werd het volgnummer
    # afgeleid uit de positie in deze lijst (`index = cursor - weggevallen`), en dat klopt alleen als
    # precies de eerste N events verdwijnen. `_cap` snoeit echter selectief — het gooit narratie weg
    # waar die ook staat — dus schoof na het snoeien alles op: een `doel`-event dat seq 0 had kwam
    # terug als seq 1, en een client die opnieuw aanhaakte kreeg juist de betekenisvolle events
    # dubbel. Nu is een seq een identiteit, geen positie.
    events: list[dict[str, Any]] = field(default_factory=list)
    # Hoeveel vluchtige events er in totaal zijn weggegooid. Puur informatief (metriek/logging); het
    # gat dat een kijker moet tonen wordt berekend uit de seq-sprong, niet hieruit.
    weggevallen: int = 0
    # Hoeveel events deze run ooit produceerde = het seq-nummer dat het volgende krijgt.
    geproduceerd: int = 0
    gestart: float = field(default_factory=time.monotonic)
    eind_op: float | None = None
    stop_gevraagd: bool = False
    taak: asyncio.Task[None] | None = None
    _wakker: asyncio.Condition = field(default_factory=asyncio.Condition)

    @property
    def loopt(self) -> bool:
        return self.status == "loopt"

    @property
    def volgende_seq(self) -> int:
        """Het seq-nummer dat het eerstvolgende event krijgt (= aantal ooit geproduceerd)."""
        return self.geproduceerd

    def samenvatting(self) -> dict[str, Any]:
        """Wat een client krijgt als hij vraagt of er nog iets loopt."""
        return {
            "run_id": self.run_id,
            "conversation_id": self.conversation_id,
            "vraag": self.vraag,
            "status": self.status,
            "volgende_seq": self.volgende_seq,
            "weggevallen": self.weggevallen,
        }


class RunRegister:
    """Houdt de lopende en recent afgeronde runs bij, één per gesprek."""

    def __init__(self, *, max_events: int = MAX_EVENTS, bewaar_s: float = BEWAAR_NA_AFLOOP_S) -> None:
        self._runs: dict[str, Run] = {}
        self._max_events = max_events
        self._bewaar_s = bewaar_s

    # -- opvragen ------------------------------------------------------------------------------

    def get(self, run_id: str, *, user_id: str | None = None) -> Run | None:
        """De run, of niets als hij niet van deze gebruiker is.

        `user_id=None` slaat de controle over — alleen voor intern gebruik, nooit vanaf een
        request. Een run van iemand anders levert `None` en dus een 404: precies zoals de api
        andermans document behandelt, zodat het bestaan niet lekt.
        """
        self._ruim_op()
        run = self._runs.get(run_id)
        if run is None:
            return None
        if user_id is not None and run.user_id != user_id:
            return None
        return run

    def actief_voor(self, conversation_id: str, *, user_id: str | None = None) -> Run | None:
        """De lopende run van dit gesprek, of de laatst afgeronde die nog binnen de bewaartermijn
        valt — beide zijn een geldige reden om aan te haken."""
        self._ruim_op()
        kandidaten = [
            r for r in self._runs.values()
            if r.conversation_id == conversation_id and (user_id is None or r.user_id == user_id)
        ]
        if not kandidaten:
            return None
        # Een lopende run wint altijd van een afgeronde; anders de meest recente.
        lopend = [r for r in kandidaten if r.loopt]
        return sorted(lopend or kandidaten, key=lambda r: r.gestart)[-1]

    # -- starten -------------------------------------------------------------------------------

    def start(
        self,
        *,
        conversation_id: str,
        vraag: str,
        maak_stroom: Callable[[Run], AsyncIterator[dict[str, Any]]],
        user_id: str = "",
    ) -> Run:
        """Registreer een run en zet hem als achtergrondtaak weg.

        `maak_stroom` krijgt de Run mee zodat de driver een stopverzoek kan zien; hij levert de
        eventstroom (in de praktijk `answer_stream`). De taak hangt bewust **niet** aan de
        request-scope: dat is de hele omkering.
        """
        self._ruim_op()
        if conversation_id:
            # Bewust ZONDER user-filter: twee beurten op één thread_id schrijven door elkaar in de
            # checkpointer, ongeacht wie ze start. De bescherming geldt de data, niet de gebruiker.
            bestaand = self.actief_voor(conversation_id)
            if bestaand is not None and bestaand.loopt:
                raise RunBestaatAl(bestaand.run_id)

        run = Run(run_id=uuid.uuid4().hex, conversation_id=conversation_id,
                  user_id=user_id, vraag=vraag)
        self._runs[run.run_id] = run
        run.taak = asyncio.create_task(self._draai(run, maak_stroom))
        return run

    async def _draai(self, run: Run, maak_stroom: Callable[[Run], AsyncIterator[dict[str, Any]]]) -> None:
        try:
            async for event in maak_stroom(run):
                await self._voeg_toe(run, event)
            nieuwe_status = "gestopt" if run.stop_gevraagd else "klaar"
        except asyncio.CancelledError:
            await self._rond_af(run, "gestopt")
            raise
        except Exception:
            # De stroom zelf saniteert zijn fouten al naar een `error`-event; komt er tóch een
            # exception doorheen, dan is dat een defect in de driver en hoort het in het log.
            logger.exception("run mislukt", extra={"categorie": "technisch", "run_id": run.run_id})
            await self._voeg_toe(run, {
                "type": "error",
                "message": "Er ging iets mis bij het beantwoorden. Probeer het opnieuw.",
            })
            nieuwe_status = "mislukt"
        await self._rond_af(run, nieuwe_status)

    async def _rond_af(self, run: Run, status: str) -> None:
        run.status = status
        run.eind_op = time.monotonic()
        async with run._wakker:
            run._wakker.notify_all()

    async def _voeg_toe(self, run: Run, event: dict[str, Any]) -> None:
        run.events.append({**event, "seq": run.geproduceerd})
        run.geproduceerd += 1
        self._cap(run)
        async with run._wakker:
            run._wakker.notify_all()

    def _cap(self, run: Run) -> None:
        """Snoei de log als hij te lang wordt — maar gooi alleen narratie weg.

        Een generieke ringbuffer zou bij een lange beurt precies het begin van het antwoord
        opeten, en dan ziet een late aanhaker een tekst die klopt noch compleet is.
        """
        if len(run.events) <= self._max_events:
            return
        teveel = len(run.events) - self._max_events
        behouden: list[dict[str, Any]] = []
        gedropt = 0
        for event in run.events:
            if gedropt < teveel and event.get("type") in VLUCHTIGE_TYPES:
                gedropt += 1
                continue
            behouden.append(event)
        run.events = behouden
        run.weggevallen += gedropt

    # -- stoppen -------------------------------------------------------------------------------

    def vraag_stop(self, run: Run) -> None:
        """Vraag om te stoppen. Bewust een vlag en géén `task.cancel()`.

        De nodes zijn synchroon en de MCP-verbinding wordt in een `finally` gesloten; die onder een
        nog draaiende executor-thread wegtrekken is vragen om kapotte verbindingen. De run stopt dus
        op de eerstvolgende grens waar de driver de vlag leest — dat kan tientallen seconden duren,
        en de UI hoort dat niet weg te moffelen.
        """
        run.stop_gevraagd = True

    # -- meekijken -----------------------------------------------------------------------------

    async def volg(self, run: Run, vanaf: int = 0) -> AsyncIterator[dict[str, Any]]:
        """Lever de events vanaf `vanaf` en volg daarna live mee.

        Elke abonnee houdt zijn eigen cursor en wacht op een `Condition` — geen `asyncio.Queue`,
        want die kun je maar één keer leegdrinken en er kunnen meerdere tabbladen meekijken.
        Losraken van deze generator laat de run ongemoeid.

        Twee dingen die eerder misgingen en waar de vorm nu op is gebouwd:

        - **Een gat blijkt uit de seq-sprong**, niet uit een teller. Het snoeien (`_cap`) haalt
          narratie weg waar die ook staat, dus "de eerste N zijn weg" was een verkeerde aanname:
          daarmee schoven de nummers op en kreeg een aanhaker betekenisvolle events dubbel.
        - **De toestandscontrole hoort onder de lock.** Stond ze erbuiten, dan kon de run afronden
          tussen `if not run.loopt` en het wachten — de `notify_all` was dan al geweest en de kijker
          bleef hangen op een run die klaar was, met een SSE-stream die nooit sloot.
        """
        cursor = vanaf
        while True:
            for event in [e for e in run.events if e.get("seq", 0) >= cursor]:
                seq = int(event.get("seq", cursor))
                if seq > cursor:
                    # Wees expliciet over het gat in plaats van stilzwijgend een verminkte tekst te
                    # leveren; dit dekt zowel te laat aanhaken als tussentijds snoeien.
                    yield {"type": "gat", "weggevallen": seq - cursor}
                yield event
                cursor = seq + 1
            async with run._wakker:
                if cursor >= run.geproduceerd and not run.loopt:
                    return
                if cursor >= run.geproduceerd:
                    await run._wakker.wait_for(
                        lambda: cursor < run.geproduceerd or not run.loopt
                    )

    # -- opruimen ------------------------------------------------------------------------------

    def _ruim_op(self) -> None:
        nu = time.monotonic()
        verlopen = [
            run_id for run_id, run in self._runs.items()
            if run.eind_op is not None and nu - run.eind_op > self._bewaar_s
        ]
        for run_id in verlopen:
            del self._runs[run_id]
