"""De orchestrator — bezit de review-lus en de state machine.

Driehoek van garanties:
  - HARD brongetrouwheid faalt → job naar `fout` (ook in review:false). Nooit stil `klaar`.
  - Schema-FOUTEN (ongeldige JAS-klasse, dangling begrip_id, …) blokkeren eveneens: eerst
    auto-correctie, blijven ze staan → `fout` (zelfde handhaving als het skill-spoor).
    Schema-WAARSCHUWINGEN blokkeren niet; die gaan als context mee naar het checkpoint.
  - Auto-correctie is GEEN ronde: her-genereren binnen één ronde, vóór het wegschrijven.
De jobstore is PostgreSQL (gedeeld). State-transities worden geserialiseerd met een atomaire
**state-CAS** (`store.claim`, één UPDATE … RETURNING): alleen de transitie NAAR een runt-state hoeft atomair,
de runt-state zelf is daarna de 'claimed'-marker zodat geen tweede worker dezelfde job oppakt.
Dit vervangt de vroegere in-process asyncio-lock en maakt de dienst **horizontaal schaalbaar**
(>1 worker/replica). Een geclaimde job draagt een `owner` + `lease_until`; de owner houdt de
lease vers via een heartbeat (`_guard`), schrijft alleen fenced (`_save`, conditioneel op nog-
eigenaar-zijn), en een periodieke reaper (`reap_once`) ruimt jobs met een verlopen lease op.
"""

from __future__ import annotations

import asyncio
import logging
import time
from uuid import uuid4

from .. import observability
from ..config import Settings
from ..contracts import (
    FoutKlasse, Job, JobFout, JobState, RondeProvenance,
    REVIEW_STATES, RUNNING_STATES, StartRequest,
)
from ..llm.base import LLMClient, LLMError
from ..llm.capture import CapturingLLMClient, gebruik_context, werk_context_bij
from ..llm.litellm_client import build_llm_client
from .. import profiles
from ..jobstore import IdConflict, JobStore
from ..rapport import bouw_rapport_async
from ..validation import (
    brongetrouwheid_check, regelspraak_brongetrouwheid_check, regelspraak_schema_check, schema_check,
)
from ..wettenbank import WettenbankClient, WettenbankError, map_artikel_naar_bron_basis, parse_jci
from . import prompts, regelspraak_steps as rs_steps, steps
from .retry import met_retry

logger = logging.getLogger(__name__)

# OpenTelemetry: tracer + metrics voor de analyse-fasen. No-op zonder de otel-extra/endpoint.
# Op module-niveau aanmaken is veilig: OTel bindt de instrumenten lazy aan de provider die
# observability.setup() straks zet (proxy-tracer/-meter).
_tracer = observability.get_tracer("wetsanalyse.engine")
_meter = observability.get_meter("wetsanalyse.engine")
_m_fase_duur = _meter.create_histogram(
    "wetsanalyse.fase.duur_ms", unit="ms", description="Duur van een orchestrator-fase in ms"
)
_m_fase_fouten = _meter.create_counter(
    "wetsanalyse.fase.fouten", description="Aantal gefaalde orchestrator-fasen per foutklasse"
)
_m_tokens = _meter.create_counter(
    "wetsanalyse.llm.tokens", description="LLM-tokenverbruik (in+out) per fase"
)


def _seed(req: StartRequest) -> str:
    """Slug-seed voor het werkgebied: de naam, of een afleiding van de eerste bron."""
    if req.naam:
        return req.naam
    b = req.bronnen[0]
    lid = f"-lid{b.lid}" if b.lid else ""
    return f"{(b.bwbId or '').lower()}-art{(b.artikel or '').lower().replace(' ', '')}{lid}"


def _naam(req: StartRequest) -> str:
    if req.naam:
        return req.naam
    b = req.bronnen[0]
    extra = f" e.a. ({len(req.bronnen)} bronnen)" if len(req.bronnen) > 1 else ""
    return f"Art. {b.artikel}{f' lid {b.lid}' if b.lid else ''}{extra}"


class LeaseVerloren(Exception):
    """De worker is zijn lease/eigenaarschap kwijt (bv. door een reaper-claim). De fase moet
    stoppen zonder verder te schrijven — een andere worker bezit de job nu."""


class WetsanalyseEngine:
    def __init__(self, settings: Settings, store: JobStore, llm: LLMClient | None, wb: WettenbankClient) -> None:
        self.s = settings
        self.store = store
        # Een geïnjecteerde client (tests/eval) overschrijft profiel-resolutie; in productie is
        # dit None en bouwt de engine per analyse een client uit het profiel van de job.
        self._llm_override = llm
        self.wb = wb
        # Per-proces id: identificeert deze worker als eigenaar van een geclaimde job. Eén engine
        # per proces (deps.get_engine is @lru_cache), dus dit id is stabiel binnen de worker.
        self.owner = uuid4().hex

    async def _llm_for(self, job: Job) -> LLMClient:
        # Wrap met de capture-decorator: legt prompt + ruwe respons vast als de toggle aan staat
        # (anders een dunne passthrough). De call-context zet de orchestrator per generatie.
        inner = self._llm_override
        if inner is None:
            cfg = await profiles.resolve_config(job.model_profile, self.s)
            inner = build_llm_client(cfg)
        return CapturingLLMClient(inner, self.store)

    # --- publieke API -----------------------------------------------------

    async def create_project(self, req: StartRequest, client_id: str):
        """Maak een Project (werkgebied met ≥1 bron) aan zonder de analyse te starten."""
        from ..project import Project as ProjectDoc
        self._valideer_bronnen(req)
        if req.model_profile:
            await profiles.ensure_exists(req.model_profile)
        # Begrensde retry: twee gelijktijdige identieke POSTs kunnen dezelfde vrije slug zien;
        # de unieke sleutel laat er één winnen, de ander leidt een nieuwe slug af (IdConflict).
        for _ in range(5):
            slug = await self.store.afgeleid_id(_seed(req))
            project = ProjectDoc(
                slug=slug,
                naam=_naam(req),
                omschrijving=req.omschrijving,
                bronnen=list(req.bronnen),
                review=req.review,
                model_profile=req.model_profile or self.s.default_model_profile,
                analysefocus=req.analysefocus or "",
                begrippenlijst=self._normaliseer_begrippenlijst(req),
                client_id=client_id,
            )
            try:
                await self.store.create_project(project, max_active=self.s.max_active_jobs)
                return project
            except IdConflict:
                continue
        raise IdConflict("Kon geen uniek project-id reserveren; probeer opnieuw.")

    async def create_job(self, req: StartRequest, client_id: str) -> Job:
        self._valideer_bronnen(req)
        if req.model_profile:
            await profiles.ensure_exists(req.model_profile)
        # Begrensde retry tegen de gelijktijdige-aanmaak-race (zie create_project). insert_job
        # maakt altijd een nieuw document, zodat de tweede POST geen bestaand project overschrijft.
        for _ in range(5):
            job_id = await self.store.afgeleid_id(_seed(req))
            job = Job(
                id=job_id,
                state=JobState.queued,
                naam=_naam(req),
                omschrijving=req.omschrijving,
                bronnen=list(req.bronnen),
                review=req.review,
                model_profile=req.model_profile or self.s.default_model_profile,
                analysefocus=req.analysefocus or "",
                begrippenlijst=self._normaliseer_begrippenlijst(req),
                client_id=client_id,
            )
            try:
                await self.store.insert_job(job, max_active=self.s.max_active_jobs)
                return job
            except IdConflict:
                continue
        raise IdConflict("Kon geen uniek analyse-id reserveren; probeer opnieuw.")

    @staticmethod
    def _normaliseer_begrippenlijst(req: StartRequest) -> list:
        """Aangeleverde begrippen krijgen bij ontbreken een genummerd id (ab1..abN), zodat de
        herkomst-registratie (`herkomst.aangeleverd_id`) altijd een aanwijsbaar doel heeft."""
        return [
            b.model_copy(update={"id": b.id or f"ab{i}"})
            for i, b in enumerate(req.begrippenlijst or [], 1)
        ]

    @staticmethod
    def _valideer_bronnen(req: StartRequest) -> None:
        if not req.bronnen:
            raise ValueError("Minstens één bron is verplicht.")
        for b in req.bronnen:
            if not b.bwbId:
                raise ValueError("bwbId is verplicht per bron (wet-only resolutie is roadmap).")

    async def run_initial(self, job_id: str) -> None:
        # CAS: claim queued → act2_runt. Faalt de claim, dan is de job al opgepakt/voorbij —
        # geen tweede worker pakt 'm op (de runt-state is de 'claimed'-marker).
        job = await self.store.claim(job_id, {JobState.queued}, JobState.act2_runt, self.owner, self.s.lease_s)
        if job is None:
            return
        await self._guard(job, "act2", self._fase_start(job))

    # Review-state → (activiteit-code in de rondes-tabel, runt-state om naar te claimen).
    _REVIEW_MAP = {
        JobState.wacht_review_act2: ("2", JobState.act2_runt),
        JobState.wacht_review_act3: ("3", JobState.act3_runt),
        JobState.wacht_review_rs_gegevens: ("rs-gegevens", JobState.rs_gegevens_runt),
        JobState.wacht_review_rs_regels: ("rs-regels", JobState.rs_regels_runt),
    }

    async def apply_feedback(self, job_id: str, feedback) -> None:
        job = await self.store.load_job(job_id)
        if job is None or job.state not in REVIEW_STATES:
            return
        activiteit, naar = self._REVIEW_MAP[job.state]
        # Claim de review-state atomair → runt; pas NA een geslaagde claim schrijven we de
        # feedback (een verloren race schrijft dan geen feedback).
        claimed = await self.store.claim(job_id, {job.state}, naar, self.owner, self.s.lease_s)
        if claimed is None:
            return
        ronde = claimed.current_ronde
        await self.store.schrijf_feedback(claimed.id, activiteit, ronde, feedback)
        if activiteit in ("2", "3"):
            await self._guard(claimed, f"act{activiteit}",
                              self._fase_feedback(claimed, activiteit, ronde, feedback))
        else:
            await self._guard(claimed, activiteit,
                              self._fase_rs_feedback(claimed, activiteit, ronde, feedback))

    async def claim_regelspraak(self, job_id: str, review: bool | None = None) -> Job | None:
        """Claim de RegelSpraak-vervolgfase **synchroon**: klaar → rs_gegevens_runt + veld-setup.
        Retourneert de geclaimde job, of None als het project niet (meer) `klaar` is (al bezig /
        verloren race). De aanroeper (router) schedulet daarna `run_regelspraak_fase`, zodat de
        DB-state al niet-terminaal is vóór de 202 — geen optimistische false-202 en geen race waarin
        de per-project events-stream meteen `done` stuurt."""
        job = await self.store.claim(
            job_id, {JobState.klaar}, JobState.rs_gegevens_runt, self.owner, self.s.lease_s
        )
        if job is None:
            return None
        job.regelspraak_review = review if review is not None else job.review
        job.current_activiteit = "rs-gegevens"
        job.current_ronde = 0
        job.error = None
        await self._save(job)
        return job

    async def run_regelspraak_fase(self, job: Job) -> None:
        """Draai de eerste rs-stap (GegevensSpraak) op een reeds via `claim_regelspraak` geclaimde job."""
        await self._guard(job, "rs-gegevens", self._fase_rs_gegevens_start(job))

    async def run_regelspraak(self, job_id: str, review: bool | None = None) -> None:
        """On-demand: start de RegelSpraak-vervolgfase op een afgeronde (`klaar`) analyse.
        Dunne wrapper (claim + fase) voor aanroepers die de claim niet apart hoeven; de router
        splitst de twee bewust om de claim synchroon vóór de 202 te leggen."""
        job = await self.claim_regelspraak(job_id, review)
        if job is None:
            return
        await self.run_regelspraak_fase(job)

    async def claim_act3(self, job_id: str) -> Job | None:
        """Claim on-demand activiteit 3 op een act2-only-afgeronde analyse: klaar → act3_runt.
        Scope gaat meteen terug naar "volledig": zodra geclaimd is de state niet meer `klaar`,
        en het bestaande retry-pad (r3>0 → wacht-op-review-act3, anders wacht-op-review-act2)
        herstelt een gefaalde run dan ongewijzigd. De router checkt scope=="act2" vóór de claim."""
        job = await self.store.claim(
            job_id, {JobState.klaar}, JobState.act3_runt, self.owner, self.s.lease_s
        )
        if job is None:
            return None
        job.scope = "volledig"
        job.current_activiteit = "3"
        job.current_ronde = 0
        job.error = None
        await self._save(job)
        return job

    async def run_act3_fase(self, job: Job) -> None:
        """Draai activiteit 3 op een reeds via `claim_act3` geclaimde job (review erft `job.review`);
        na de act3-review/akkoord wordt het rapport langs het normale pad herbouwd."""
        await self._guard(job, "act3", self._fase_act3_start(job))

    async def run_act3(self, job_id: str) -> None:
        """On-demand: voer activiteit 3 alsnog uit op een act2-only-afgeronde analyse.
        Dunne wrapper (claim + fase); de router splitst de twee om de claim vóór de 202 te leggen."""
        job = await self.claim_act3(job_id)
        if job is None:
            return
        await self.run_act3_fase(job)

    async def retry(self, job_id: str) -> None:
        job = await self.store.load_job(job_id)
        if job is None or job.state != JobState.fout:
            return
        # Faalde de regelspraak-vervolgfase, dan herstellen we bínnen die fase (de analyse zelf was
        # al `klaar`). current_activiteit (gezet bij de claim) wijst de fase aan, ook vóór de eerste
        # ronde-write.
        if job.current_activiteit in ("rs-gegevens", "rs-regels"):
            await self._retry_regelspraak(job)
            return
        r2 = await self.store.hoogste_ronde(job.id, "2")
        r3 = await self.store.hoogste_ronde(job.id, "3")
        # Doelstate vóór de claim bepalen. Een verse job (geen rondes) gaat direct naar act2_runt
        # i.p.v. via een queued-tussenstap, zodat er geen venster is waarin niets de job claimt.
        if r3 > 0:
            naar, activiteit, ronde = JobState.wacht_review_act3, "3", r3
        elif r2 > 0:
            naar, activiteit, ronde = JobState.wacht_review_act2, "2", r2
        else:
            naar, activiteit, ronde = JobState.act2_runt, None, 0
        claimed = await self.store.claim(job_id, {JobState.fout}, naar, self.owner, self.s.lease_s)
        if claimed is None:
            return
        try:
            claimed.error = None
            if activiteit is not None:
                claimed.current_activiteit, claimed.current_ronde = activiteit, ronde
            await self.store.save_job(claimed)
        except Exception:  # noqa: BLE001 — laat de job in een herstelbare state i.p.v. stil hangen
            logger.exception("Retry van job %s kon de state niet herstellen", job_id)
            return
        if naar == JobState.act2_runt:
            await self._guard(claimed, "act2", self._fase_start(claimed))

    async def reconcile_startup(self) -> None:
        """Migratie-/herstelvangnet bij opstart. Onder >1 replica mag een opstartende worker NIET
        zomaar alle runt-jobs doodverklaren (die kunnen van een levende collega zijn). We geven
        daarom alleen runt-jobs *zonder* lease (pre-upgrade of een crash waarbij het lease-veld
        nooit gezet werd) een verlopen lease, zodat de reaper ze opruimt. Jobs met een geldige
        lease blijven ongemoeid; verloopt die lease, dan pakt de reaper ze alsnog op."""
        n = await self.store.markeer_lease_loze_running()
        if n:
            logger.info("Reconcile: %d lease-loze runt-job(s) gemarkeerd voor de reaper.", n)
        await self._reap_verweesde_queued()

    async def reap_once(self) -> None:
        """Eén reaper-ronde: claim elke runt-job met een verlopen lease naar `fout`. De claim is
        atomair én vereist een verlopen lease, dus een job van een levende worker (verse lease)
        wordt nooit gekaapt. Ruimt daarnaast verweesde `queued`-jobs op (zie hieronder)."""
        for job_id in await self.store.lijst_verlopen_running():
            claimed = await self.store.claim(
                job_id, RUNNING_STATES, JobState.fout, self.owner, self.s.lease_s,
                vereist_verlopen_lease=True,
            )
            if claimed is None:
                continue  # lease intussen verlengd of al opgepakt door een andere reaper
            logger.warning("Reaper: job %s had een verlopen lease → fout (onderbroken).", job_id)
            await self._fail(claimed, claimed.current_activiteit or "intern", FoutKlasse.intern,
                             "Onderbroken: lease verlopen (worker weg of gecrasht).")
        await self._reap_verweesde_queued()

    async def _reap_verweesde_queued(self) -> None:
        """Vangnet voor de `queued`-dead-end: crasht het proces tussen de commit van
        `POST /v1/projects` en de claim in `run_initial`, dan blijft de job anders eeuwig
        `queued` (geen retry/delete mogelijk; telt mee in het quotum). Drempel = de lease:
        de claim volgt normaal binnen milliseconden op de create, dus een `queued` zonder
        owner die ouder is dan de lease is aantoonbaar wees. De atomaire claim verliest
        netjes van een gelijktijdige run_initial-claim (state is dan al niet meer queued)."""
        for job_id in await self.store.lijst_verweesde_queued(self.s.lease_s):
            claimed = await self.store.claim(
                job_id, {JobState.queued}, JobState.fout, self.owner, self.s.lease_s
            )
            if claimed is None:
                continue  # intussen alsnog opgepakt (of al door een andere reaper gemarkeerd)
            logger.warning("Reaper: job %s bleef verweesd in queued → fout.", job_id)
            await self._fail(claimed, "start", FoutKlasse.intern,
                             "Onderbroken vóór de start (worker weg of gecrasht); "
                             "probeer opnieuw via retry of verwijder de analyse.")

    # --- fasen (coroutines, uitgevoerd binnen _guard) ---------------------

    async def _fase_start(self, job: Job) -> None:
        job.state = JobState.act2_runt
        await self._save(job)
        await self._set_fase(job, "wettekst-ophalen")
        # Haal per bron de letterlijke tekst op (deterministisch, via de MCP). Eén bron met een
        # MCP-mis laat de hele job falen (brongetrouwheid) — geen stille lege context.
        bron_bases: list[dict] = []
        for i, b in enumerate(job.bronnen, 1):
            data = await self._met_retry(lambda b=b: self.wb.artikel(b.bwbId, b.artikel, b.lid))
            bron_bases.append(map_artikel_naar_bron_basis(data, f"br{i}", b.lid))
        await self._genereer_act2_vers(job, 1, bron_bases)

    async def _fase_feedback(self, job: Job, activiteit: str, ronde: int, feedback) -> None:
        if feedback.status == "akkoord-afronden":
            # Bewust afronden ná activiteit 2 (contract-validatie borgt: alleen act 2, zonder
            # opmerkingen). Zelfde promotie-garantie als akkoord, maar rechtstreeks naar het
            # rapport; scope="act2" markeert de analyse als act2-only (RegelSpraak-gate + UI).
            if not await self._herassert_brongetrouw(job, activiteit):
                return
            job.scope = "act2"
            await self._bouw_rapport(job)
            return
        if feedback.is_akkoord_zonder_opmerkingen() or ronde >= self.s.max_rondes:
            if not await self._herassert_brongetrouw(job, activiteit):
                return  # onbetrouwbare (via retry hervatte) ronde → fout i.p.v. promoveren
            await self._advance_akkoord(job, activiteit)
            return
        job.state = JobState.act2_runt if activiteit == "2" else JobState.act3_runt
        await self._save(job)
        llm = await self._llm_for(job)
        vorige = await self.store.lees_analyse(job.id, activiteit, ronde) or {}
        # Context voor prompt + merge: act-2 herziet op de brongetrouwe bronnen van ronde 1;
        # act-3 op de goedgekeurde act-2 (leden-tekst + bron-index, zelfde context als vers).
        context = (await self._context_act2(job)) if activiteit == "2" else (await self._act2_akkoord(job))
        fb = feedback.model_dump()

        async def maak():
            return await steps.herzie(
                llm, activiteit, context, ronde + 1, vorige, fb,
                omschrijving=job.omschrijving,
                analysefocus=job.analysefocus or None,
                begrippenlijst=self._begrippenlijst(job),
            )

        await self._afronden_ronde(job, activiteit, ronde + 1, maak)

    async def _advance_akkoord(self, job: Job, activiteit: str) -> None:
        if activiteit == "2":
            await self._fase_act3_start(job)
        else:
            await self._bouw_rapport(job)

    async def _fase_act3_start(self, job: Job) -> None:
        """Start activiteit 3 (ronde 1) op de goedgekeurde act-2 — vanuit de normale flow
        (`_advance_akkoord`) of on-demand (`run_act3_fase` op een act2-only-`klaar`)."""
        job.state = JobState.act3_runt
        await self._save(job)
        llm = await self._llm_for(job)
        act2 = await self._act2_akkoord(job)

        async def maak():
            return await steps.genereer_act3(
                llm, 1, act2,
                omschrijving=job.omschrijving,
                analysefocus=job.analysefocus or None,
                begrippenlijst=self._begrippenlijst(job),
            )

        await self._afronden_ronde(job, "3", 1, maak)

    async def _herassert_brongetrouw(self, job: Job, activiteit: str) -> bool:
        """Her-bevestig de HARDE brongetrouwheid-invariant vóór een akkoord-promotie. Een ronde die
        langs de normale weg in review belandt is altijd brongetrouw, maar via `retry` kan een eerder
        op brongetrouwheid gefaalde (en tóch weggeschreven) ronde in de review-akkoord-state hervatten.
        Zonder deze her-check zou 'akkoord' dan een onherleidbaar model promoveren — in strijd met de
        garantie 'HARD brongetrouwheid → fout, nooit stil door'. No-op voor geldige modellen."""
        is_rs = activiteit in ("rs-gegevens", "rs-regels")
        n = await self.store.hoogste_ronde(job.id, activiteit)
        analyse = await self.store.lees_analyse(job.id, activiteit, n) or {}
        if is_rs:
            # Ook hier de ingest meegeven: een via retry hervatte ronde met dangling herkomst mag
            # niet alsnog promoveren (zelfde garantie als de afronding van een verse ronde).
            rapport = await self.store.lees_rapport(job.id) or {}
            schendingen = regelspraak_brongetrouwheid_check(
                analyse, activiteit, self._rs_gegevens_context(rapport)
            )
        else:
            schendingen = brongetrouwheid_check(analyse, activiteit)
        if schendingen:
            stap = activiteit if is_rs else f"act{activiteit}"
            await self._fail(job, stap, FoutKlasse.validatie,
                             "Promotie geweigerd — brongetrouwheid faalt: " + "; ".join(schendingen))
            return False
        return True

    # --- generatie van één ronde (incl. auto-correctie) -------------------

    def _werkgebied(self, job: Job) -> dict:
        return {"naam": job.naam, "hoofdvraag": job.analysefocus or "",
                "omschrijving": job.omschrijving or "", "scoping": ""}

    def _begrippenlijst(self, job: Job) -> list[dict] | None:
        """De aangeleverde begrippenlijst als plain dicts (prompt- en validatiecontext)."""
        if not job.begrippenlijst:
            return None
        return [b.model_dump() for b in job.begrippenlijst]

    async def _context_act2(self, job: Job) -> dict:
        """De act-2-aggregaat van ronde 1 (brongetrouwe bronnen) — merge-basis voor act-2-revise."""
        return await self.store.lees_analyse(job.id, "2", 1) or {}

    async def _act2_akkoord(self, job: Job) -> dict:
        """De goedgekeurde act-2 = de hóógste ronde (herziene rondes zijn volledige, brongetrouwe
        aggregaten dankzij de revise-merge) — de input voor act-3. Ronde 1 nemen zou de
        review-feedback op act-2 negeren."""
        n = await self.store.hoogste_ronde(job.id, "2")
        return await self.store.lees_analyse(job.id, "2", n) or {}

    async def _genereer_act2_vers(self, job: Job, ronde: int, bron_bases: list[dict]) -> None:
        """Verse act-2: per bron de verwijzing-inventaris (fase 2a) + begrensde fetch (één keer),
        daarna per bron markeren/classificeren en tot één werkgebied-aggregaat samenvoegen."""
        llm = await self._llm_for(job)
        per_bron: list[tuple[dict, dict, dict]] = []
        inv_in = inv_out = 0
        with gebruik_context(project_slug=job.id, activiteit="2", ronde=ronde, fase="inventaris"):
            for bb in bron_bases:
                await self._set_fase(job, "verwijzingen-inventariseren")
                inv_res = await self._met_retry(lambda bb=bb: steps.inventariseer_verwijzingen(llm, bb))
                inv_in += inv_res.tokens_in
                inv_out += inv_res.tokens_out
                await self._set_fase(job, "verwijzingen-volgen")
                opgehaald = await self._volg_verwijzingen(bb, inv_res.data)
                per_bron.append((bb, inv_res.data, opgehaald))

        async def maak():
            bronnen, tin, tout, prov0 = [], 0, 0, None
            for bb, inv, opg in per_bron:
                bron_dict, prov = await steps.genereer_act2_bron(
                    llm, bb, ronde, job.analysefocus or None, inv, opg
                )
                bronnen.append(bron_dict)
                tin += prov["tokens_in"]
                tout += prov["tokens_out"]
                prov0 = prov0 or prov
            analyse = {
                "werkgebied": self._werkgebied(job),
                "analysefocus": job.analysefocus or "",
                "bronnen": bronnen,
            }
            prov = dict(prov0 or {})
            prov["tokens_in"], prov["tokens_out"] = tin, tout
            return analyse, prov

        await self._afronden_ronde(job, "2", ronde, maak, extra_tokens=(inv_in, inv_out))

    async def _afronden_ronde(self, job: Job, activiteit: str, ronde: int, maak, extra_tokens=(0, 0)) -> None:
        """Gemeenschappelijke afronding van één ronde: budget-check, auto-correctie op harde
        brongetrouwheid, schema-check, wegschrijven, en de state-overgang (review of door)."""
        if self.s.llm_token_budget > 0:
            gebruikt = sum(p.tokens_in + p.tokens_out for p in job.provenance)
            if gebruikt >= self.s.llm_token_budget:
                await self._fail(
                    job, f"act{activiteit}", FoutKlasse.quota,
                    f"LLM-tokenbudget ({self.s.llm_token_budget}) overschreden na {gebruikt} tokens.",
                )
                return

        # Act-3-context (eenmalig vóór de lus): de goedgekeurde act-2 activeert de dekkings-/
        # markering-id-checks, de aangeleverde begrippenlijst de herkomst-checks.
        act2 = (await self._act2_akkoord(job)) if activiteit == "3" else None
        bl = self._begrippenlijst(job)

        def _schema(a: dict) -> tuple[list[str], list[str]]:
            if activiteit == "3":
                return schema_check(a, activiteit, act2=act2,
                                    begrippenlijst={"begrippen": bl} if bl else None)
            return schema_check(a, activiteit)

        await self._set_fase(job, "llm-generatie")
        # Tokens van verworpen auto-correctie-pogingen tellen mee (budget/usage-aggregatie).
        weggegooid_in = weggegooid_out = 0
        with gebruik_context(project_slug=job.id, activiteit=activiteit, ronde=ronde,
                             poging=1, fase="generatie"):
            analyse, prov = await self._met_retry(maak)
            pogingen = 0
            # Auto-correctie regenereert op harde brongetrouwheid-schendingen én op blokkerende
            # schema-fouten (ongeldige JAS-klasse, dangling begrip_id, …) — dezelfde handhaving
            # als het skill-spoor (validate_analyse exit 2). Waarschuwingen blokkeren niet.
            while pogingen < self.s.max_autocorrectie and (
                brongetrouwheid_check(analyse, activiteit) or _schema(analyse)[0]
            ):
                pogingen += 1
                werk_context_bij(poging=pogingen + 1, fase="auto-correctie")
                await self._set_fase(job, "auto-correctie")
                weggegooid_in += prov.get("tokens_in", 0)
                weggegooid_out += prov.get("tokens_out", 0)
                analyse, prov = await self._met_retry(maak)
        # Tel eenmalig de inventaris-tokens (fase 2a) plus de verworpen pogingen bij de ronde.
        prov["tokens_in"] += extra_tokens[0] + weggegooid_in
        prov["tokens_out"] += extra_tokens[1] + weggegooid_out

        await self._set_fase(job, "brongetrouwheid-check")
        schendingen = brongetrouwheid_check(analyse, activiteit)
        await self._set_fase(job, "schema-check")
        fouten, waarschuwingen = _schema(analyse)

        await self._set_fase(job, "analyse-wegschrijven")
        await self.store.schrijf_analyse(job.id, activiteit, ronde, analyse)
        job.provenance.append(RondeProvenance(**prov))
        _m_tokens.add(prov.get("tokens_in", 0) + prov.get("tokens_out", 0), {"stap": f"act{activiteit}"})
        job.current_activiteit = activiteit
        job.current_ronde = ronde
        job.waarschuwingen = schendingen + fouten + waarschuwingen
        await self._save(job)

        if schendingen:
            await self._fail(
                job, f"act{activiteit}", FoutKlasse.validatie,
                "Brongetrouwheid faalt na auto-correctie: " + "; ".join(schendingen),
            )
            return
        if fouten:
            # Schema-fouten blokkeren, ook in review:false — gelijke handhaving met het
            # skill-spoor, waar validate_analyse.py met exit 2 de review-server tegenhoudt.
            await self._fail(
                job, f"act{activiteit}", FoutKlasse.validatie,
                "Schema-fouten na auto-correctie: " + "; ".join(fouten),
            )
            return
        if job.review:
            job.state = JobState.wacht_review_act2 if activiteit == "2" else JobState.wacht_review_act3
            await self._save(job)
            await self._set_fase(job, None)  # wachtstate: geen lopende functiefase
            return
        await self._advance_akkoord(job, activiteit)

    # --- rapport ----------------------------------------------------------

    async def _bouw_rapport(self, job: Job) -> None:
        job.state = JobState.bouwt
        await self._save(job)
        await self._set_fase(job, "reviewlog")
        reviewlog_act2 = await self._reviewlog(job, "2")
        reviewlog_act3 = await self._reviewlog(job, "3")
        await self._set_fase(job, "aandachtspunten")
        aandachtspunten = await self._aandachtspunten(job)
        await self._set_fase(job, "rapport-wegschrijven")
        rapport = await bouw_rapport_async(
            self.store,
            job.id,
            reviewlog_act2=reviewlog_act2,
            reviewlog_act3=reviewlog_act3,
            aandachtspunten=aandachtspunten,
        )
        await self.store.schrijf_rapport(job.id, rapport)
        job.state = JobState.klaar
        await self._save(job)
        await self._set_fase(job, None)  # terminaal: geen lopende functiefase

    async def _reviewlog(self, job: Job, activiteit: str) -> str:
        n = await self.store.hoogste_ronde(job.id, activiteit)
        if n == 0:
            return ""  # activiteit niet uitgevoerd (act2-only-afronding) — geen log-regel
        if not job.review:
            return f"Review overgeslagen (review:false); {n} ronde(n) autonoom gegenereerd."
        if n <= 1:
            return "1 ronde — direct akkoord, geen wijzigingen."
        return f"{n} rondes — feedback per ronde verwerkt tot akkoord."

    async def _aandachtspunten(self, job: Job) -> str:
        n = await self.store.hoogste_ronde(job.id, "3")
        a3 = await self.store.lees_analyse(job.id, "3", n) or {}
        punten = list(a3.get("validatiepunten") or [])
        for b in a3.get("begrippen", []) + a3.get("afleidingsregels", []):
            if (b.get("twijfel") or "").strip():
                punten.append(f"{b.get('naam', b.get('id', '?'))}: {b['twijfel']}")
        if job.waarschuwingen:
            punten.append("Mechanische waarschuwingen: " + "; ".join(job.waarschuwingen))
        return "\n".join(f"- {p}" for p in punten) if punten else ""

    # --- RegelSpraak-vervolgfase (GegevensSpraak → regels → model) --------

    def _rs_review(self, job: Job) -> bool:
        return job.regelspraak_review if job.regelspraak_review is not None else job.review

    async def _retry_regelspraak(self, job: Job) -> None:
        """Herstel een gefaalde regelspraak-fase: hervat in de review-state als er al een ronde is,
        anders herstart de generatie van de betreffende stap."""
        n_rg = await self.store.hoogste_ronde(job.id, "rs-regels")
        n_gs = await self.store.hoogste_ronde(job.id, "rs-gegevens")
        if n_rg > 0:
            naar, stap, ronde = JobState.wacht_review_rs_regels, "rs-regels", n_rg
        elif n_gs > 0:
            naar, stap, ronde = JobState.wacht_review_rs_gegevens, "rs-gegevens", n_gs
        else:
            naar, stap, ronde = JobState.rs_gegevens_runt, None, 0
        claimed = await self.store.claim(job.id, {JobState.fout}, naar, self.owner, self.s.lease_s)
        if claimed is None:
            return
        try:
            claimed.error = None
            if stap is not None:
                claimed.current_activiteit, claimed.current_ronde = stap, ronde
            else:
                claimed.current_activiteit, claimed.current_ronde = "rs-gegevens", 0
            await self.store.save_job(claimed)
        except Exception:  # noqa: BLE001
            logger.exception("Retry regelspraak van job %s kon de state niet herstellen", job.id)
            return
        if naar == JobState.rs_gegevens_runt:
            await self._guard(claimed, "rs-gegevens", self._fase_rs_gegevens_start(claimed))

    def _rs_gegevens_context(self, rapport: dict) -> dict:
        """Trim het rapport tot wat de GegevensSpraak-stap voedt: werkgebied + begrippen +
        afleidingsregels + per bron de identificatie (incl. `pad`), de letterlijke `leden`,
        de `verwijzingen`, de brondefinitie-markeringen én de markeringen waar een begrip/regel
        via `markering_ids` op steunt. Zelfde trim als de skill-ingest (`ingest_rapport.py`)."""
        gerefereerd: set[str] = set()
        for groep in ("begrippen", "afleidingsregels"):
            for item in (rapport.get(groep) or []):
                gerefereerd.update(m for m in (item.get("markering_ids") or []) if m)
        bronnen = []
        for b in rapport.get("bronnen") or []:
            markeringen = b.get("markeringen") or []
            bron = {
                "bron_id": b.get("bron_id"), "label": b.get("label"),
                "bwbId": b.get("bwbId"), "artikel": b.get("artikel"), "lid": b.get("lid"),
                "versiedatum": b.get("versiedatum"), "bronreferentie": b.get("bronreferentie"),
                "pad": b.get("pad"),
                # Pariteit met de skill-ingest: de letterlijke leden-tekst en de verwijzingen
                # gaan mee, zodat het dienst-spoor met dezelfde brongetrouwe context
                # formaliseert (de prompt-token-guard bewaakt de omvang).
                "leden": b.get("leden") or [],
                "verwijzingen": b.get("verwijzingen") or [],
                "brondefinities": [
                    m for m in markeringen if m.get("klasse") == "Brondefinitie"
                ],
                "gekoppelde_markeringen": [
                    m for m in markeringen
                    if m.get("klasse") != "Brondefinitie" and m.get("id") in gerefereerd
                ],
            }
            bronnen.append(bron)
        return {
            "werkgebied": rapport.get("werkgebied") or {},
            "bronnen": bronnen,
            "begrippen": rapport.get("begrippen") or [],
            "afleidingsregels": rapport.get("afleidingsregels") or [],
        }

    async def _rs_regels_context(self, job: Job) -> dict:
        """Context voor de regels-stap: het objectmodel van de hoogste GegevensSpraak-ronde +
        de afleidingsregels uit het rapport."""
        n = await self.store.hoogste_ronde(job.id, "rs-gegevens")
        gs_model = await self.store.lees_analyse(job.id, "rs-gegevens", n) or {}
        rapport = await self.store.lees_rapport(job.id) or {}
        basis = self._rs_gegevens_context(rapport)
        return {
            "werkgebied": gs_model.get("werkgebied") or rapport.get("werkgebied") or {},
            "gegevensspraak": gs_model.get("gegevensspraak") or {},
            "afleidingsregels": rapport.get("afleidingsregels") or [],
            "bronnen": basis["bronnen"],
        }

    async def _fase_rs_gegevens_start(self, job: Job) -> None:
        job.state = JobState.rs_gegevens_runt
        await self._save(job)
        rapport = await self.store.lees_rapport(job.id) or {}
        context = self._rs_gegevens_context(rapport)
        llm = await self._llm_for(job)

        async def maak():
            return await rs_steps.genereer_gegevens(llm, 1, context)

        await self._afronden_rs_ronde(job, "rs-gegevens", 1, maak)

    async def _afronden_rs_ronde(self, job: Job, stap: str, ronde: int, maak) -> None:
        """Afronding van één regelspraak-ronde: budget-check, auto-correctie op de harde
        herkomst-invariant, zachte schema-check, wegschrijven en de overgang (review of door)."""
        if self.s.llm_token_budget > 0:
            gebruikt = sum(p.tokens_in + p.tokens_out for p in job.provenance)
            if gebruikt >= self.s.llm_token_budget:
                await self._fail(job, stap, FoutKlasse.quota,
                                 f"LLM-tokenbudget ({self.s.llm_token_budget}) overschreden na "
                                 f"{gebruikt} tokens.")
                return

        # De wetsanalyse-als-ingest: voedt de herkomst-cross-check (dangling = hard, dekking = zacht).
        rapport = await self.store.lees_rapport(job.id) or {}
        ingest = self._rs_gegevens_context(rapport)

        fase = "regelspraak-gegevens-generatie" if stap == "rs-gegevens" else "regelspraak-regels-generatie"
        await self._set_fase(job, fase)
        with gebruik_context(project_slug=job.id, activiteit=stap, ronde=ronde,
                             poging=1, fase="generatie"):
            analyse, prov = await self._met_retry(maak)
            pogingen = 0
            while pogingen < self.s.max_autocorrectie and regelspraak_brongetrouwheid_check(analyse, stap, ingest):
                pogingen += 1
                werk_context_bij(poging=pogingen + 1, fase="auto-correctie")
                await self._set_fase(job, "auto-correctie")
                analyse, prov = await self._met_retry(maak)

        await self._set_fase(job, "brongetrouwheid-check")
        schendingen = regelspraak_brongetrouwheid_check(analyse, stap, ingest)
        await self._set_fase(job, "schema-check")
        fouten, waarschuwingen = regelspraak_schema_check(analyse, stap, ingest)

        await self._set_fase(job, "analyse-wegschrijven")
        await self.store.schrijf_analyse(job.id, stap, ronde, analyse)
        job.provenance.append(RondeProvenance(**prov))
        _m_tokens.add(prov.get("tokens_in", 0) + prov.get("tokens_out", 0), {"stap": stap})
        job.current_activiteit = stap
        job.current_ronde = ronde
        job.waarschuwingen = schendingen + fouten + waarschuwingen
        await self._save(job)

        if schendingen:
            await self._fail(job, stap, FoutKlasse.validatie,
                             "Herkomst ontbreekt na auto-correctie: " + "; ".join(schendingen))
            return
        if self._rs_review(job):
            job.state = (JobState.wacht_review_rs_gegevens if stap == "rs-gegevens"
                         else JobState.wacht_review_rs_regels)
            await self._save(job)
            await self._set_fase(job, None)
            return
        await self._advance_rs_akkoord(job, stap)

    async def _advance_rs_akkoord(self, job: Job, stap: str) -> None:
        if stap == "rs-gegevens":
            job.state = JobState.rs_regels_runt
            await self._save(job)
            context = await self._rs_regels_context(job)
            llm = await self._llm_for(job)

            async def maak():
                return await rs_steps.genereer_regels(llm, 1, context)

            await self._afronden_rs_ronde(job, "rs-regels", 1, maak)
        else:
            await self._bouw_regelspraak(job)

    async def _fase_rs_feedback(self, job: Job, stap: str, ronde: int, feedback) -> None:
        if feedback.is_akkoord_zonder_opmerkingen() or ronde >= self.s.max_rondes:
            if not await self._herassert_brongetrouw(job, stap):
                return  # onbetrouwbare (via retry hervatte) ronde → fout i.p.v. promoveren
            await self._advance_rs_akkoord(job, stap)
            return
        job.state = JobState.rs_gegevens_runt if stap == "rs-gegevens" else JobState.rs_regels_runt
        await self._save(job)
        llm = await self._llm_for(job)
        vorige = await self.store.lees_analyse(job.id, stap, ronde) or {}
        if stap == "rs-gegevens":
            rapport = await self.store.lees_rapport(job.id) or {}
            context = self._rs_gegevens_context(rapport)
        else:
            context = await self._rs_regels_context(job)
        fb = feedback.model_dump()

        async def maak():
            return await rs_steps.herzie(llm, stap, ronde + 1, context, vorige, fb)

        await self._afronden_rs_ronde(job, stap, ronde + 1, maak)

    async def _bouw_regelspraak(self, job: Job) -> None:
        job.state = JobState.rs_bouwt
        await self._save(job)
        await self._set_fase(job, "regelspraak-bouwt")
        n_gs = await self.store.hoogste_ronde(job.id, "rs-gegevens")
        n_rg = await self.store.hoogste_ronde(job.id, "rs-regels")
        gs = await self.store.lees_analyse(job.id, "rs-gegevens", n_gs) or {}
        rg = await self.store.lees_analyse(job.id, "rs-regels", n_rg) or {}
        model = {
            "werkgebied": gs.get("werkgebied") or rg.get("werkgebied") or {},
            "gegevensspraak": gs.get("gegevensspraak") or {},
            "regels": rg.get("regels") or [],
            "reviewlog_gegevensspraak": await self._rs_reviewlog(job, "rs-gegevens"),
            "reviewlog_regels": await self._rs_reviewlog(job, "rs-regels"),
            "validatiepunten": rg.get("validatiepunten") or [],
            "reviewlog": {
                "gegevensspraak": {"rondes": await self._rs_reviewlog_rondes(job, "rs-gegevens")},
                "regels": {"rondes": await self._rs_reviewlog_rondes(job, "rs-regels")},
            },
        }
        await self.store.schrijf_regelspraak(job.id, model)
        job.state = JobState.rs_klaar
        await self._save(job)
        await self._set_fase(job, None)

    async def _rs_reviewlog(self, job: Job, stap: str) -> str:
        n = await self.store.hoogste_ronde(job.id, stap)
        if not self._rs_review(job):
            return f"Review overgeslagen (review:false); {n} ronde(n) autonoom gegenereerd."
        if n <= 1:
            return "1 ronde — direct akkoord, geen wijzigingen."
        return f"{n} rondes — feedback per ronde verwerkt tot akkoord."

    async def _rs_reviewlog_rondes(self, job: Job, stap: str) -> list[dict]:
        rondes = await self.store.lees_alle_rondes(job.id, stap)
        out = []
        for nr in sorted(rondes, key=lambda x: int(x)):
            fb = rondes[nr].feedback or {}
            out.append({
                "ronde": int(nr),
                "items": fb.get("items") or {},
                "algemeen": (fb.get("algemeen") or "").strip(),
                "status": fb.get("status", ""),
            })
        return out

    # --- helpers ----------------------------------------------------------

    async def _met_retry(self, maak):
        """Bounded retry op transiënte LLM/MCP-fouten met de geconfigureerde knoppen."""
        return await met_retry(
            maak,
            max_retries=self.s.transient_max_retries,
            backoff=self.s.transient_backoff_s,
            max_backoff=self.s.transient_max_backoff_s,
        )

    async def _volg_verwijzingen(self, basis: dict, inventaris: dict) -> dict:
        """Niveau B — haal de te-volgen verwijzingen op (diepte 1, begrensd tot de fetch-cap).
        Een gefaalde fetch degradeert STIL: de verwijzing blijft 'gesignaleerd', de job faalt
        nooit op een verwezen artikel. Retourneert {target: opgehaalde tekst} als act-2b-context.
        """
        cap = self.s.max_verwijzing_fetches
        if cap <= 0:
            return {}
        opgehaald: dict[str, str] = {}
        gezien: set[tuple] = set()
        for v in (inventaris.get("verwijzingen") or []):
            if len(opgehaald) >= cap:
                break
            if not v.get("volgen"):
                continue
            doel = v.get("doel") or {}
            parsed = parse_jci(doel.get("target") or "")
            if parsed is None:
                continue
            bwb, artikel, lid = parsed
            sleutel = (bwb.upper(), artikel, lid)
            if sleutel in gezien:
                continue
            gezien.add(sleutel)
            try:
                data = await self.wb.artikel(bwb, artikel, lid)
            except Exception as e:  # noqa: BLE001 — best-effort; nooit de job laten falen
                logger.info("Verwijzing-fetch %s art %s overgeslagen: %s", bwb, artikel, e)
                continue
            teksten = [f"Lid {l.get('lid','')}: {l.get('tekst','')}".strip()
                       for l in (data.get("leden") or []) if l.get("tekst")]
            if teksten:
                label = doel.get("target") or f"{bwb} artikel {artikel}"
                opgehaald[label] = "\n".join(teksten)
        return opgehaald

    async def _fail(self, job: Job, stap: str, klasse: FoutKlasse, bericht: str) -> None:
        job.state = JobState.fout
        job.error = JobFout(stap=stap, ronde=job.current_ronde or None, klasse=klasse, bericht=bericht)
        # Fenced (net als _save): schrijf alleen zolang deze worker de job nog bezit. Bij een
        # verloren lease bezit een andere worker (bv. de reaper) de job — diens state niet clobberen.
        if not await self.store.save_job(job, owner=self.owner):
            logger.warning("Job %s: fout-state niet geschreven — lease/owner intussen kwijt "
                           "(een andere worker bezit de job).", job.id)
            return
        await self._set_fase(job, None)  # fout: geen lopende functiefase meer tonen

    async def _save(self, job: Job) -> None:
        """Fenced state-write: schrijft alleen als deze worker de job nog bezit. Verloren lease
        (bv. door een reaper-claim) → LeaseVerloren, zodat de fase stopt i.p.v. een andere worker
        te overschrijven."""
        if not await self.store.save_job(job, owner=self.owner):
            raise LeaseVerloren(job.id)

    async def _set_fase(self, job: Job, fase: str | None) -> None:
        """Observerende fase-tik voor het live dashboard (zie PostgresStore.set_current_fase). Strikt
        BEST-EFFORT: een verloren lease (False) of welke fout dan ook breekt de analyse NIET af en
        verandert de control-flow niet — de fase is puur diagnostisch. De canonieke fase-strings
        worden 1-op-1 gespiegeld in frontend/lib/fasen.ts."""
        try:
            await self.store.set_current_fase(job.id, fase, self.owner)
        except Exception:  # noqa: BLE001 — observerend; nooit de analyse laten struikelen
            logger.debug("Fase-tik %r voor %s overgeslagen.", fase, job.id, exc_info=True)

    # Zoveel opeenvolgende gefaalde heartbeat-ticks (bv. een transiënte DB-hapering) tolereren we
    # voordat de heartbeat opgeeft. Eén hikje mag niet betekenen dat de reaper een levende job kaapt.
    _HEARTBEAT_MAX_MISSERS = 3

    async def _heartbeat(self, job_id: str) -> None:
        """Houd de lease vers terwijl de fase loopt, zodat de reaper een levende job niet kaapt.
        Tikt op lease_s/2. Raakt de owner de job kwijt, dan stopt de heartbeat; de eerstvolgende
        fenced `_save` breekt de fase dan netjes af. Een transiënte fout (bv. een DB-hapering)
        doodt de heartbeat niet direct — pas na N opeenvolgende missers geeft hij op."""
        interval = max(self.s.lease_s / 2, 1)
        missers = 0
        try:
            while True:
                await asyncio.sleep(interval)
                try:
                    if not await self.store.verleng_lease(job_id, self.owner, self.s.lease_s):
                        return  # owner/lease definitief kwijt — geen fout, gewoon stoppen
                    missers = 0
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001 — transiënt: tolereren tot de misser-cap
                    missers += 1
                    logger.debug("Heartbeat-tick voor %s mislukt (%d/%d).",
                                 job_id, missers, self._HEARTBEAT_MAX_MISSERS, exc_info=True)
                    if missers >= self._HEARTBEAT_MAX_MISSERS:
                        logger.warning("Heartbeat voor %s gestopt na %d opeenvolgende missers.",
                                       job_id, missers)
                        return
        except asyncio.CancelledError:
            return

    async def _guard(self, job: Job, stap: str, coro) -> None:
        """Voer een fase uit (met lease-heartbeat) en vertaal faalklassen naar een terminale
        `fout`-state. Verliest de worker zijn lease, dan stopt de fase zonder de job te raken."""
        hb = asyncio.create_task(self._heartbeat(job.id))
        start = time.perf_counter()
        fout_klasse: str | None = None
        with _tracer.start_as_current_span(
            "wetsanalyse.fase",
            attributes={"wetsanalyse.job_id": job.id, "wetsanalyse.stap": stap},
        ) as span:
            try:
                await coro
            except LeaseVerloren:
                logger.warning("Job %s: lease verloren tijdens %s — afgebroken (andere worker bezit "
                               "de job nu).", job.id, stap)
            except WettenbankError as e:
                fout_klasse = "mcp"
                span.record_exception(e)
                logger.warning("Job %s faalt op %s (MCP): %s", job.id, stap, e)
                await self._fail(job, stap, FoutKlasse.mcp, str(e))
            except LLMError as e:
                # LLMError-meldingen zijn door onze eigen adapter geformuleerd (JSON-reparatie,
                # PromptTooLarge) en veilig om aan de client te tonen.
                fout_klasse = "llm"
                span.record_exception(e)
                logger.warning("Job %s faalt op %s (LLM): %s", job.id, stap, e)
                await self._fail(job, stap, FoutKlasse.llm, str(e))
            except Exception as e:  # noqa: BLE001
                # Een rauwe provider-/interne fout kan endpoint-URL's, headers of (delen van) een
                # key bevatten — die hoort in het server-log, niet in job.error richting de client
                # (zelfde sanitisatie als de admin-verbindingstest).
                fout_klasse = "intern"
                span.record_exception(e)
                logger.exception("Job %s faalt op %s (intern)", job.id, stap)
                await self._fail(job, stap, FoutKlasse.intern,
                                 "Interne fout bij het uitvoeren van deze stap — zie het server-log "
                                 "voor details. Probeer opnieuw via retry.")
            finally:
                _m_fase_duur.record(
                    round((time.perf_counter() - start) * 1000, 1), {"stap": stap}
                )
                if fout_klasse:
                    _m_fase_fouten.add(1, {"stap": stap, "klasse": fout_klasse})
                    span.set_attribute("wetsanalyse.fout_klasse", fout_klasse)
                hb.cancel()
                try:
                    await hb
                except asyncio.CancelledError:
                    pass
                except Exception:  # noqa: BLE001 — een gefaalde heartbeat mag de fase-afronding niet breken
                    logger.debug("Heartbeat van job %s eindigde met een fout.", job.id, exc_info=True)
