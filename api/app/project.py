"""Domeinmodel voor een analyse-project (plain Pydantic; persistentie via app/db.py + de store).

Eén project draagt de state-machine + de afgeleide telemetrie. De gegenereerde artefacten
(rondes, feedback) staan in de aparte `rondes`-tabel en het eindrapport in een JSON-kolom; de
store vult `rapport` bij het laden en laat `rondes` leeg (consumenten lezen rondes uitsluitend via
de store-methoden, nooit via dit attribuut).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from .contracts import BegripInvoer, BronInput, JobFout, JobState, RondeProvenance


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RondeData(BaseModel):
    analyse: dict = Field(default_factory=dict)
    feedback: dict | None = None


class Project(BaseModel):
    slug: str
    naam: str = ""
    omschrijving: str = ""

    bronnen: list[BronInput] = Field(default_factory=list)
    analysefocus: str = ""
    # Aangeleverde bestaande begrippenlijst (suggestieve invoer voor activiteit 3).
    begrippenlijst: list[BegripInvoer] = Field(default_factory=list)
    review: bool = True
    model_profile: str = ""
    client_id: str = ""

    state: JobState = JobState.queued
    # "act2" = bewust afgerond zonder activiteit 3; terug naar "volledig" bij de on-demand act3-claim.
    scope: Literal["volledig", "act2"] = "volledig"
    current_activiteit: Literal["2", "3", "rs-gegevens", "rs-regels"] | None = None
    current_ronde: int = 0
    # Observerend, voor het live dashboard: de fijnmazige fase BINNEN een runt/bouwt-state
    # (bijv. "llm-generatie", "verwijzingen-volgen"). Bewust géén state-machine-veld — alleen
    # via store.set_current_fase geschreven, zodat fase-tikken de state-CAS en de
    # updated-sortering niet raken. None buiten een runt/bouwt.
    current_fase: str | None = None
    current_fase_sinds: datetime | None = None
    waarschuwingen: list[str] = Field(default_factory=list)
    error: JobFout | None = None
    provenance: list[RondeProvenance] = Field(default_factory=list)

    # Concurrency: alleen beheerd via store.claim() en de lease-heartbeat — NOOIT via save_job.
    # owner = per-proces id van de worker die de job verwerkt; lease_until = tot wanneer die
    # claim geldig is (verloopt → de reaper mag de job opruimen).
    owner: str | None = None
    lease_until: datetime | None = None

    created: datetime = Field(default_factory=_utcnow)
    updated: datetime = Field(default_factory=_utcnow)

    rondes: dict[str, dict[str, RondeData]] = Field(default_factory=dict)
    rapport: dict | None = None
    # RegelSpraak-vervolgfase: het eind-model.json (gevuld via store.schrijf_regelspraak) en of die
    # fase met review-checkpoints draait (None = nog niet gestart / erft review).
    regelspraak: dict | None = None
    regelspraak_review: bool | None = None

    def touch(self) -> None:
        self.updated = _utcnow()

    def to_job(self):
        from .contracts import Job
        return Job(
            id=self.slug,
            naam=self.naam,
            omschrijving=self.omschrijving,
            bronnen=self.bronnen,
            review=self.review,
            model_profile=self.model_profile,
            analysefocus=self.analysefocus,
            begrippenlijst=self.begrippenlijst,
            client_id=self.client_id,
            regelspraak_review=self.regelspraak_review,
            scope=self.scope,
            state=self.state,
            current_activiteit=self.current_activiteit,
            current_ronde=self.current_ronde,
            waarschuwingen=self.waarschuwingen,
            error=self.error,
            provenance=self.provenance,
            created=self.created.isoformat(),
            updated=self.updated.isoformat(),
        )
