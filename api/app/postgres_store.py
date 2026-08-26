"""Async PostgreSQL-jobstore via SQLAlchemy Core — de concrete JobStore-implementatie (zie jobstore.py).

De mechanismen:
  - atomaire state-CAS (`claim`/`verleng_lease`/`set_current_fase`) → één `UPDATE ... WHERE ... RETURNING`;
  - owner-fencing → een extra `owner = :owner` in de WHERE;
  - ronde-immutabiliteit → een aparte `rondes`-tabel met (project, activiteit, ronde) als sleutel;
  - de tijd komt uit Python (`db.utcnow`), niet uit SQL, zodat de queries portable blijven (SQLite-tests).

Kritisch (net als voorheen): save_job overschrijft uitsluitend state-machine-velden — nooit
rondes/rapport/naam/omschrijving.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError

from . import db
from .config import Settings
import re

from .contracts import (
    Analyse2, Analyse3, BegripInvoer, BronInput, Feedback, Job, JobState, QUOTA_VRIJE_STATES,
    RUNNING_STATES, RondeProvenance,
)
from .jobstore import IdConflict
from .project import Project, RondeData

logger = logging.getLogger(__name__)

# Velden die save_job mag overschrijven. Bewust ZONDER owner/lease_until: die worden uitsluitend
# door claim()/verleng_lease() beheerd, zodat een stale Job-snapshot de lease nooit kan overschrijven.
_STATE_FIELDS = (
    "state", "scope", "current_activiteit", "current_ronde", "waarschuwingen",
    "error", "provenance", "bronnen", "review",
    "model_profile", "analysefocus", "client_id", "regelspraak_review",
)


def _serialize(value):
    """pydantic/enum → JSON-vriendelijke waarde voor een JSON(B)-kolom."""
    if hasattr(value, "value") and isinstance(value, JobState):
        return value.value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")
    if isinstance(value, list):
        return [x.model_dump(mode="python") if hasattr(x, "model_dump") else x for x in value]
    return value


def _state_values(job: Job) -> dict:
    """De state-machine-velden van een Job als kolom→waarde-blok (geserialiseerd)."""
    return {field: _serialize(getattr(job, field, None)) for field in _STATE_FIELDS}


def _create_values(obj) -> dict:
    """Kolom→waarde-blok voor het aanmaken van een projects-rij. Één gedeelde bron voor zowel
    `insert_job` (Job) als `create_project` (Project), zodat de twee aanmaakpaden niet stil uiteen
    kunnen lopen (ze schrijven gegarandeerd dezelfde kolommen). Werkt op elk object met de
    create-time-velden + de _STATE_FIELDS (Job én Project dragen die)."""
    return {
        "naam": getattr(obj, "naam", None),
        "omschrijving": obj.omschrijving,
        "begrippenlijst": [b.model_dump() for b in obj.begrippenlijst],
        **_state_values(obj),
    }


def _row_to_project(row) -> Project:
    """Bouw een Project-domeinmodel uit een projects-rij (datetimes UTC-aware, JSON → modellen)."""
    m = dict(row)
    return Project(
        slug=m["slug"],
        naam=m["naam"] or "",
        omschrijving=m["omschrijving"] or "",
        bronnen=[BronInput(**b) for b in (m["bronnen"] or [])],
        analysefocus=m["analysefocus"] or "",
        begrippenlijst=[BegripInvoer(**b) for b in (m.get("begrippenlijst") or [])],
        review=m["review"],
        model_profile=m["model_profile"] or "",
        client_id=m["client_id"] or "",
        state=JobState(m["state"]),
        scope=m.get("scope") or "volledig",
        current_activiteit=m["current_activiteit"],
        current_ronde=m["current_ronde"] or 0,
        current_fase=m["current_fase"],
        current_fase_sinds=db.aware(m["current_fase_sinds"]),
        waarschuwingen=list(m["waarschuwingen"] or []),
        error=m["error"],
        provenance=[RondeProvenance(**p) for p in (m["provenance"] or [])],
        owner=m["owner"],
        lease_until=db.aware(m["lease_until"]),
        created=db.aware(m["created"]),
        updated=db.aware(m["updated"]),
        # .get zodat een lichte projectie (list_projects(light=True), zonder de zware JSONB-kolommen)
        # niet KeyErrort — het dashboard heeft rapport/regelspraak niet nodig.
        rapport=m.get("rapport"),
        regelspraak=m.get("regelspraak"),
        regelspraak_review=m.get("regelspraak_review"),
    )


class PostgresStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # --- id-afleiding ---

    async def afgeleid_id(self, seed: str) -> str:
        basis = re.sub(r"[^a-z0-9]+", "-", (seed or "").lower()).strip("-") or "werkgebied"
        kandidaat, n = basis, 1
        async with db.get_engine().connect() as conn:
            while True:
                row = await conn.execute(
                    select(db.projects.c.slug).where(db.projects.c.slug == kandidaat)
                )
                if row.first() is None:
                    return kandidaat
                n += 1
                kandidaat = f"{basis}-{n}"

    # --- job (state-machine view) ---

    async def save_job(self, job: Job, *, owner: str | None = None) -> bool:
        """Schrijf de state-machine-velden. Met `owner` is de write *fenced*: hij landt alleen als
        die owner de job nog bezit (verloren lease → False, geen clobber). Return True = geschreven.

        Schrijft nooit rondes/rapport/naam/omschrijving, zodat een verouderde snapshot die
        artefacten niet kan wissen.

        Insert-if-missing geldt ALLEEN voor de niet-fenced (owner=None) write. Een fenced write
        (owner gezet, zoals `_save`/`_fail` tijdens een lopende run) doet nooit een insert: is de rij
        tussentijds verwijderd (delete-race op een `queued`-job die net geclaimd werd), dan levert de
        write False i.p.v. het project te 'laten herrijzen'."""
        now = db.utcnow()
        values = _state_values(job)
        async with db.get_engine().begin() as conn:
            if owner is None:
                bestaat = (await conn.execute(
                    select(db.projects.c.slug).where(db.projects.c.slug == job.id)
                )).first() is not None
                if not bestaat:
                    await conn.execute(insert(db.projects).values(
                        slug=job.id, created=now, updated=now, **values
                    ))
                    return True
                res = await conn.execute(
                    update(db.projects).where(db.projects.c.slug == job.id).values(updated=now, **values)
                )
                return res.rowcount == 1
            res = await conn.execute(
                update(db.projects)
                .where(db.projects.c.slug == job.id, db.projects.c.owner == owner)
                .values(updated=now, **values)
            )
            return res.rowcount == 1

    async def set_current_fase(self, job_id: str, fase: str | None, owner: str) -> bool:
        """Observerende, owner-fenced single-field update voor het live dashboard. Schrijft
        UITSLUITEND current_fase (+ _sinds) — nooit `updated`, `state`, owner of lease, zodat de
        fijnmazige fase-tikken de homepage-sortering (op `updated`) en de state-machine ongemoeid
        laten. Verkeerde/verloren owner → geen match → False (best-effort aan de aanroepkant)."""
        async with db.get_engine().begin() as conn:
            res = await conn.execute(
                update(db.projects)
                .where(db.projects.c.slug == job_id, db.projects.c.owner == owner)
                .values(current_fase=fase, current_fase_sinds=db.utcnow() if fase else None)
            )
        return res.rowcount == 1

    async def _handhaaf_active_quota(self, conn, client_id: str, max_active: int) -> None:
        """ATOMAIRE per-client grens op niet-terminale analyses, bínnen de insert-transactie.
        Vervangt een check-dan-insert (TOCTOU): op Postgres serialiseert een advisory xact-lock
        gelijktijdige aanmaak per client (auto-release bij commit/rollback), zodat de telling onder
        READ COMMITTED niet ontdubbelt. Op SQLite (tests) is geen lock nodig — writes zijn al
        geserialiseerd. Goedkope COUNT i.p.v. het laden+deserialiseren van alle projecten."""
        if max_active <= 0:
            return
        from .ratelimit import QuotaExceeded
        if db.get_engine().url.get_backend_name() == "postgresql":
            await conn.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
                {"k": f"actieve-jobs:{client_id}"},
            )
        actief = (await conn.execute(
            select(func.count()).select_from(db.projects).where(
                db.projects.c.client_id == client_id,
                # Tel alleen lopende/in-review ANALYSE-runs; terminale states én de on-demand
                # RegelSpraak-vervolgfase tellen niet mee (anders vult formaliseren het quotum).
                db.projects.c.state.notin_([s.value for s in QUOTA_VRIJE_STATES]),
            )
        )).scalar_one()
        if actief >= max_active:
            raise QuotaExceeded(
                f"Te veel lopende analyses (max {max_active}); wacht tot er één klaar is."
            )

    async def insert_job(self, job: Job, *, max_active: int = 0) -> None:
        """Maak altijd een nieuw project-document aan (nooit bijwerken). Werpt IdConflict als de
        slug al bestaat — de aanroeper handelt de race af. Met `max_active`>0 wordt de per-client
        grens op niet-terminale analyses atomair in dezelfde transactie afgedwongen (QuotaExceeded)."""
        now = db.utcnow()
        try:
            async with db.get_engine().begin() as conn:
                await self._handhaaf_active_quota(conn, job.client_id, max_active)
                await conn.execute(insert(db.projects).values(
                    slug=job.id, created=now, updated=now, **_create_values(job),
                ))
        except IntegrityError:
            raise IdConflict(f"slug bestaat al: {job.id}")

    async def create_project(self, project: Project, *, max_active: int = 0) -> None:
        """Maak een volledig project-document aan (incl. naam/omschrijving). Werpt IdConflict bij
        een dubbele slug. Met `max_active`>0 geldt dezelfde atomaire per-client grens als insert_job."""
        now = db.utcnow()
        try:
            async with db.get_engine().begin() as conn:
                await self._handhaaf_active_quota(conn, project.client_id, max_active)
                await conn.execute(insert(db.projects).values(
                    slug=project.slug, created=now, updated=now, **_create_values(project),
                ))
        except IntegrityError:
            raise IdConflict(f"slug bestaat al: {project.slug}")

    async def claim(
        self,
        job_id: str,
        van: set[JobState],
        naar: JobState,
        owner: str,
        lease_s: int,
        *,
        vereist_verlopen_lease: bool = False,
    ) -> Job | None:
        """Atomaire state-transitie (CAS): zet de job van een van de `van`-states naar `naar` en
        claim 'm voor `owner` met een verse lease. Slaagt de match → de aanroeper bezit de job
        (return Job); geen match (andere state/andere worker bezig) → None."""
        now = db.utcnow()
        stmt = (
            update(db.projects)
            .where(
                db.projects.c.slug == job_id,
                db.projects.c.state.in_([s.value for s in van]),
            )
        )
        if vereist_verlopen_lease:
            stmt = stmt.where(db.projects.c.lease_until < now)
        stmt = stmt.values(
            state=naar.value,
            owner=owner,
            lease_until=now + timedelta(seconds=lease_s),
            updated=now,
        ).returning(db.projects)
        async with db.get_engine().begin() as conn:
            row = (await conn.execute(stmt)).mappings().first()
        return _row_to_project(row).to_job() if row is not None else None

    async def verleng_lease(self, job_id: str, owner: str, lease_s: int) -> bool:
        """Heartbeat: verleng de lease, maar UITSLUITEND zolang `owner` de job nog bezit en hij in
        een runt-state staat. Geen match → de worker is zijn lease kwijt (return False)."""
        now = db.utcnow()
        async with db.get_engine().begin() as conn:
            res = await conn.execute(
                update(db.projects)
                .where(
                    db.projects.c.slug == job_id,
                    db.projects.c.owner == owner,
                    db.projects.c.state.in_([s.value for s in RUNNING_STATES]),
                )
                .values(lease_until=now + timedelta(seconds=lease_s))
            )
        return res.rowcount == 1

    async def lijst_verlopen_running(self) -> list[str]:
        """Ids van runt-jobs met een verlopen lease — input voor de reaper."""
        now = db.utcnow()
        async with db.get_engine().connect() as conn:
            rows = await conn.execute(
                select(db.projects.c.slug).where(
                    db.projects.c.state.in_([s.value for s in RUNNING_STATES]),
                    db.projects.c.lease_until < now,
                )
            )
        return [r[0] for r in rows.all()]

    async def lijst_verweesde_queued(self, ouder_dan_s: int) -> list[str]:
        """Ids van verweesde `queued`-jobs: nooit geclaimd (geen owner) en ouder dan de drempel.
        Crasht het proces tussen de create-commit en de run_initial-claim, dan blijft de job
        anders eeuwig `queued` (buiten reaper, retry en quota-vrijgave) — input voor de reaper."""
        grens = db.utcnow() - timedelta(seconds=ouder_dan_s)
        async with db.get_engine().connect() as conn:
            rows = await conn.execute(
                select(db.projects.c.slug).where(
                    db.projects.c.state == JobState.queued.value,
                    db.projects.c.owner.is_(None),
                    db.projects.c.updated < grens,
                )
            )
        return [r[0] for r in rows.all()]

    async def markeer_lease_loze_running(self) -> int:
        """Migratie-/herstelvangnet: geef runt-jobs zónder lease (pre-upgrade of na een crash waar
        het lease-veld nooit gezet werd) een verlopen lease, zodat de reaper ze oppakt. Jobs met een
        nog-geldige lease blijven ongemoeid."""
        now = db.utcnow()
        async with db.get_engine().begin() as conn:
            res = await conn.execute(
                update(db.projects)
                .where(
                    db.projects.c.state.in_([s.value for s in RUNNING_STATES]),
                    db.projects.c.lease_until.is_(None),
                )
                .values(lease_until=now - timedelta(seconds=1))
            )
        return res.rowcount

    async def load_job(self, job_id: str) -> Job | None:
        p = await self.load_project(job_id)
        return p.to_job() if p else None

    async def list_jobs(self, client_id: str | None = None) -> list[Job]:
        return [p.to_job() for p in await self.list_projects(client_id)]

    # --- analyse (immutabel per ronde) ---

    async def _project_bestaat(self, conn, job_id: str) -> bool:
        row = await conn.execute(select(db.projects.c.slug).where(db.projects.c.slug == job_id))
        return row.first() is not None

    async def _ronde_row(self, conn, job_id: str, activiteit: str, ronde: int):
        return (await conn.execute(
            select(db.rondes).where(
                db.rondes.c.project_slug == job_id,
                db.rondes.c.activiteit == activiteit,
                db.rondes.c.ronde == ronde,
            )
        )).mappings().first()

    async def hoogste_ronde(self, job_id: str, activiteit: str) -> int:
        async with db.get_engine().connect() as conn:
            res = await conn.execute(
                select(func.max(db.rondes.c.ronde)).where(
                    db.rondes.c.project_slug == job_id,
                    db.rondes.c.activiteit == activiteit,
                )
            )
        return res.scalar() or 0

    async def schrijf_analyse(self, job_id: str, activiteit: str, ronde: int, data: dict) -> None:
        async with db.get_engine().begin() as conn:
            if not await self._project_bestaat(conn, job_id):
                raise KeyError(f"Onbekend project: {job_id}")
            bestaand = await self._ronde_row(conn, job_id, activiteit, ronde)
            if bestaand is not None and bestaand["analyse"]:
                raise PermissionError(f"Ronde {ronde} act{activiteit} is immutabel.")
            if bestaand is None:
                await conn.execute(insert(db.rondes).values(
                    project_slug=job_id, activiteit=activiteit, ronde=ronde, analyse=data,
                ))
            else:
                await conn.execute(
                    update(db.rondes).where(
                        db.rondes.c.project_slug == job_id,
                        db.rondes.c.activiteit == activiteit,
                        db.rondes.c.ronde == ronde,
                    ).values(analyse=data)
                )
            await conn.execute(
                update(db.projects).where(db.projects.c.slug == job_id).values(updated=db.utcnow())
            )

    async def lees_analyse(self, job_id: str, activiteit: str, ronde: int) -> dict | None:
        async with db.get_engine().connect() as conn:
            row = await self._ronde_row(conn, job_id, activiteit, ronde)
        if row is None or not row["analyse"]:
            return None
        return row["analyse"]

    async def lees_analyse_model(self, job_id: str, activiteit: str, ronde: int):
        data = await self.lees_analyse(job_id, activiteit, ronde)
        if data is None:
            return None
        return (Analyse2 if activiteit == "2" else Analyse3).model_validate(data)

    async def lees_alle_rondes(self, job_id: str, activiteit: str) -> dict[str, RondeData]:
        async with db.get_engine().connect() as conn:
            rows = (await conn.execute(
                select(db.rondes).where(
                    db.rondes.c.project_slug == job_id,
                    db.rondes.c.activiteit == activiteit,
                )
            )).mappings().all()
        return {
            str(r["ronde"]): RondeData(analyse=r["analyse"] or {}, feedback=r["feedback"])
            for r in rows
        }

    # --- feedback ---

    async def schrijf_feedback(self, job_id: str, activiteit: str, ronde: int, fb: Feedback) -> None:
        async with db.get_engine().begin() as conn:
            if not await self._project_bestaat(conn, job_id):
                raise KeyError(f"Onbekend project: {job_id}")
            bestaand = await self._ronde_row(conn, job_id, activiteit, ronde)
            if bestaand is None:
                await conn.execute(insert(db.rondes).values(
                    project_slug=job_id, activiteit=activiteit, ronde=ronde,
                    analyse={}, feedback=fb.model_dump(),
                ))
            else:
                await conn.execute(
                    update(db.rondes).where(
                        db.rondes.c.project_slug == job_id,
                        db.rondes.c.activiteit == activiteit,
                        db.rondes.c.ronde == ronde,
                    ).values(feedback=fb.model_dump())
                )
            await conn.execute(
                update(db.projects).where(db.projects.c.slug == job_id).values(updated=db.utcnow())
            )

    async def lees_feedback(self, job_id: str, activiteit: str, ronde: int) -> Feedback | None:
        async with db.get_engine().connect() as conn:
            row = await self._ronde_row(conn, job_id, activiteit, ronde)
        if row is None or not row["feedback"]:
            return None
        return Feedback.model_validate(row["feedback"])

    # --- rapport (JSON-kolom op het project) ---

    async def schrijf_rapport(self, job_id: str, rapport: dict) -> None:
        async with db.get_engine().begin() as conn:
            res = await conn.execute(
                update(db.projects).where(db.projects.c.slug == job_id)
                .values(rapport=rapport, updated=db.utcnow())
            )
        # Geen exception (best-effort), maar niet stil: is het project intussen verdwenen
        # (bv. door een delete-race tijdens de run), dan is de rapport-write verloren — log dat.
        if res.rowcount == 0:
            logger.warning("Rapport-write voor %s raakte geen rij — project verdwenen tijdens de run?", job_id)

    async def lees_rapport(self, job_id: str) -> dict | None:
        async with db.get_engine().connect() as conn:
            res = await conn.execute(
                select(db.projects.c.rapport).where(db.projects.c.slug == job_id)
            )
        row = res.first()
        return row[0] if row is not None else None

    # --- regelspraak-model (JSON-kolom op het project) ---

    async def schrijf_regelspraak(self, job_id: str, model: dict) -> None:
        async with db.get_engine().begin() as conn:
            res = await conn.execute(
                update(db.projects).where(db.projects.c.slug == job_id)
                .values(regelspraak=model, updated=db.utcnow())
            )
        if res.rowcount == 0:
            logger.warning("Regelspraak-write voor %s raakte geen rij — project verdwenen tijdens de run?", job_id)

    async def lees_regelspraak(self, job_id: str) -> dict | None:
        async with db.get_engine().connect() as conn:
            res = await conn.execute(
                select(db.projects.c.regelspraak).where(db.projects.c.slug == job_id)
            )
        row = res.first()
        return row[0] if row is not None else None

    # --- project CRUD ---

    async def load_project(self, job_id: str) -> Project | None:
        async with db.get_engine().connect() as conn:
            row = (await conn.execute(
                select(db.projects).where(db.projects.c.slug == job_id)
            )).mappings().first()
        return _row_to_project(row) if row is not None else None

    async def list_projects(
        self, client_id: str | None = None, *, limit: int | None = None, offset: int = 0,
        light: bool = False,
    ) -> list[Project]:
        # light=True laat de zware JSONB-kolommen (rapport/regelspraak) uit de SELECT — die
        # deserialiseren is duur en het dashboard/de projectenlijst gebruiken ze niet. Het
        # aggregate-SSE pollt dit elke ~5s per open dashboard, dus dat telt op.
        if light:
            kolommen = [c for c in db.projects.c if c.name not in ("rapport", "regelspraak")]
            stmt = select(*kolommen)
        else:
            stmt = select(db.projects)
        if client_id is not None:
            stmt = stmt.where(db.projects.c.client_id == client_id)
        stmt = stmt.order_by(db.projects.c.updated.desc()).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        async with db.get_engine().connect() as conn:
            rows = (await conn.execute(stmt)).mappings().all()
        return [_row_to_project(r) for r in rows]

    async def delete_project(self, job_id: str) -> bool:
        async with db.get_engine().begin() as conn:
            await conn.execute(delete(db.rondes).where(db.rondes.c.project_slug == job_id))
            await conn.execute(delete(db.llm_calls).where(db.llm_calls.c.project_slug == job_id))
            res = await conn.execute(delete(db.projects).where(db.projects.c.slug == job_id))
        return res.rowcount == 1

    # --- LLM-call-capture (prompt + ruwe respons, voor analyse) ---

    async def schrijf_llm_call(self, call: dict) -> None:
        """Leg één feitelijke LLM-call vast. Best-effort: capture mag de analyse nooit breken."""
        waarden = {
            "project_slug": call.get("project_slug") or "",
            "activiteit": call.get("activiteit") or "",
            "ronde": int(call.get("ronde") or 0),
            "poging": int(call.get("poging") or 1),
            "fase": call.get("fase") or "",
            "model": call.get("model") or "",
            "provider": call.get("provider") or "",
            "system_prompt": call.get("system_prompt") or "",
            "user_prompt": call.get("user_prompt") or "",
            "response_text": call.get("response_text") or "",
            "tokens_in": int(call.get("tokens_in") or 0),
            "tokens_out": int(call.get("tokens_out") or 0),
            "ok": bool(call.get("ok", True)),
            "error": call.get("error"),
            "tijdstip": db.utcnow(),
        }
        async with db.get_engine().begin() as conn:
            await conn.execute(insert(db.llm_calls).values(**waarden))

    async def lijst_llm_calls(self, project_slug: str) -> list[dict]:
        async with db.get_engine().connect() as conn:
            rows = (await conn.execute(
                select(db.llm_calls)
                .where(db.llm_calls.c.project_slug == project_slug)
                .order_by(db.llm_calls.c.id)
            )).mappings().all()
        return [dict(r) for r in rows]

    # --- generieke runtime-instellingen (key/value) ---

    async def lees_app_setting(self, key: str):
        async with db.get_engine().connect() as conn:
            res = await conn.execute(
                select(db.app_settings.c.value).where(db.app_settings.c.key == key)
            )
        row = res.first()
        return row[0] if row is not None else None

    async def schrijf_app_setting(self, key: str, value) -> None:
        now = db.utcnow()
        async with db.get_engine().begin() as conn:
            bestaat = (await conn.execute(
                select(db.app_settings.c.key).where(db.app_settings.c.key == key)
            )).first()
            if bestaat is None:
                await conn.execute(insert(db.app_settings).values(key=key, value=value, updated=now))
            else:
                await conn.execute(
                    update(db.app_settings).where(db.app_settings.c.key == key)
                    .values(value=value, updated=now)
                )
