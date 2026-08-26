"""De kanonieke analyse-resource (gemount onder /v1/projects) — CRUD + SSE state-updates.

Eén URL-conventie voor sub-resources (`/ronde/{act}/{n}`). Vervangt de eerdere losse
/analyses-router (geconsolideerd: één resource, geen dubbele oppervlakte).

POST   /v1/projects                     — maak project aan en start analyse (202 + Location)
GET    /v1/projects?limit=&offset=      — lijst eigen projecten (beknopt, gepagineerd)
GET    /v1/projects/{id}                — volledig project-object
DELETE /v1/projects/{id}                — verwijder (terminal, review-state of queued; runt → 409)
POST   /v1/projects/{id}/feedback       — review-feedback
POST   /v1/projects/{id}/retry          — herstart vanuit fout
GET    /v1/projects/{id}/rapport        — rapport JSON
GET    /v1/projects/{id}/rapport.md     — rapport Markdown
GET    /v1/projects/{id}/ronde/{act}/{n} — analyse-JSON van één ronde
GET    /v1/projects/{id}/events         — SSE state-updates (max 10 min)
GET    /v1/projects/events              — SSE geaggregeerde dashboard-updates (alle eigen projecten)
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse, StreamingResponse

from ..auth import require_client
from ..contracts import (
    ACTIVITEIT_CODES, CreateAccepted, Feedback, FeedbackAccepted, Job, JobState, JobSummary,
    Rapport, RegelspraakModel, RegelspraakStart, REVIEW_STATES, TERMINAL_STATES, StartRequest,
)
from ..deps import get_engine, get_store, schedule
from ..jobstore import IdConflict, JobStore
from ..ratelimit import QuotaExceeded, rate_limited_client

router = APIRouter(prefix="/projects", tags=["projects"])


async def _project_or_404(store: JobStore, project_id: str, client_id: str):
    """Laadt het project en dwingt eigenaarschap af. 404 (niet 403) bij mismatch, zodat
    het bestaan van andermans projecten niet lekt."""
    p = await store.load_project(project_id)
    if p is None or p.client_id != client_id:
        raise HTTPException(status_code=404, detail=f"Onbekend project: {project_id}")
    return p


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=CreateAccepted)
async def maak_project(
    req: StartRequest, response: Response, client_id: str = Depends(rate_limited_client)
):
    try:
        engine = get_engine()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"Engine niet beschikbaar: {e}")
    try:
        project = await engine.create_project(req, client_id)
    except QuotaExceeded as e:
        raise HTTPException(status_code=429, detail=str(e))
    except IdConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    schedule(engine.run_initial(project.slug))
    response.headers["Location"] = f"/v1/projects/{project.slug}"
    return CreateAccepted(id=project.slug, naam=project.naam, state=project.state)


@router.get("", response_model=list[JobSummary])
async def lijst_projecten(
    client_id: str = Depends(require_client),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    projects = await get_store().list_projects(client_id, limit=limit, offset=offset)
    return [
        JobSummary(
            id=p.slug, naam=p.naam, state=p.state,
            bronnen=p.bronnen, updated=p.updated.isoformat(),
            current_fase=p.current_fase, model_profile=p.model_profile,
            scope=p.scope,
            tokens_in=sum(r.tokens_in for r in p.provenance),
            tokens_out=sum(r.tokens_out for r in p.provenance),
        )
        for p in projects
    ]


def _dashboard_payload(p) -> dict:
    """Compacte, JSON-klare momentopname van één project voor het live dashboard. Telt de tokens
    uit de provenance op (zelfde bron als usage.py) en plat de fout uit tot drie velden. JobState/
    FoutKlasse zijn str-enums, dus direct json-serialiseerbaar."""
    return {
        "id": p.slug,
        "naam": p.naam,
        "bronnen": [b.model_dump() for b in p.bronnen],
        "state": p.state,
        "scope": p.scope,
        "current_activiteit": p.current_activiteit,
        "current_ronde": p.current_ronde,
        "current_fase": p.current_fase,
        "current_fase_sinds": p.current_fase_sinds.isoformat() if p.current_fase_sinds else None,
        "created": p.created.isoformat(),
        "updated": p.updated.isoformat(),
        "model_profile": p.model_profile,
        "tokens_in": sum(r.tokens_in for r in p.provenance),
        "tokens_out": sum(r.tokens_out for r in p.provenance),
        "error": (
            {"stap": p.error.stap, "klasse": p.error.klasse, "bericht": p.error.bericht}
            if p.error else None
        ),
    }


async def _dashboard_poll(
    store: JobStore, client_id: str, seen: dict[str, dict]
) -> tuple[list[str], dict[str, dict]]:
    """Eén poll-ronde: vergelijk de huidige projecten van de client met de vorige momentopname `seen`
    en geef (a) de te-emitten SSE-frames en (b) de bijgewerkte `seen` terug. Alleen gewijzigde
    projecten krijgen een `data:`-frame; verdwenen (verwijderde) projecten een `event: removed`.
    Apart van de stream-lus gehouden zodat dit zonder oneindige SSE getest kan worden."""
    projects = await store.list_projects(client_id, limit=100, light=True)
    huidige = {p.slug for p in projects}
    frames: list[str] = []
    nieuw: dict[str, dict] = {}
    for p in projects:
        payload = _dashboard_payload(p)
        nieuw[p.slug] = payload
        if seen.get(p.slug) != payload:
            frames.append(f"data: {json.dumps(payload)}\n\n")
    for verdwenen in seen.keys() - huidige:
        # `removed` alleen bij écht verwijderd: een project dat enkel buiten de poll-limiet
        # (top-100 op `updated`) valt bestaat nog en mag niet live uit de UI verdwijnen.
        p = await store.load_project(verdwenen)
        if p is None or p.client_id != client_id:
            frames.append(f"event: removed\ndata: {json.dumps({'id': verdwenen})}\n\n")
        else:
            nieuw[verdwenen] = seen[verdwenen]  # blijven volgen; geen vals removed-event
    return frames, nieuw


@router.get("/events")
async def alle_project_events(request: Request, client_id: str = Depends(require_client)):
    """SSE — geaggregeerde state-/fase-updates van ALLE projecten van deze client, voor het live
    dashboard. Eén poll-lus (elke 5s, max ~10 min; EventSource herverbindt daarna automatisch) i.p.v.
    één stream per project; per project alleen `data:` bij een gewijzigde momentopname. LET OP: deze
    route staat bewust vóór `/{project_id}`, anders vangt die path-param het pad 'events'."""
    store = get_store()

    async def stream():
        seen: dict[str, dict] = {}
        for _ in range(120):
            if await request.is_disconnected():
                return
            frames, seen = await _dashboard_poll(store, client_id, seen)
            if frames:
                for f in frames:
                    yield f
            else:
                # Heartbeat (SSE-commentaarregel): houdt bytes stromen bij een stille poll, zodat de
                # Next.js-BFF (undici) de verbinding niet met UND_ERR_BODY_TIMEOUT verbreekt.
                yield ": keep-alive\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{project_id}", response_model=Job)
async def project_detail(project_id: str, client_id: str = Depends(require_client)):
    p = await _project_or_404(get_store(), project_id, client_id)
    return p.to_job()


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def verwijder_project(project_id: str, client_id: str = Depends(require_client)):
    store = get_store()
    p = await _project_or_404(store, project_id, client_id)
    # Verwijderen mag vanuit een eindstaat (klaar/fout), vanuit een review-pauze
    # (de analist kan een lopende analyse tijdens de review weggooien) én vanuit `queued`
    # (escape-hatch voor een verweesde job — normaal claimt run_initial binnen milliseconden,
    # dus een zichtbaar `queued` project is vrijwel zeker wees). In een lopende (runt-)state
    # draait er nog een achtergrondtaak die het document muteert → niet verwijderen (409).
    if p.state not in TERMINAL_STATES | REVIEW_STATES | {JobState.queued}:
        raise HTTPException(
            status_code=409,
            detail=f"Kan alleen verwijderen vanuit een review- of eindstaat; staat nu op: {p.state}",
        )
    await store.delete_project(project_id)


@router.post("/{project_id}/feedback", status_code=status.HTTP_202_ACCEPTED, response_model=FeedbackAccepted)
async def geef_feedback(project_id: str, feedback: Feedback, client_id: str = Depends(rate_limited_client)):
    store = get_store()
    p = await _project_or_404(store, project_id, client_id)
    job = p.to_job()
    if job.state not in REVIEW_STATES:
        raise HTTPException(status_code=409, detail=f"Feedback alleen in review-state; nu: {job.state}")
    verwacht = {
        JobState.wacht_review_act2: "2",
        JobState.wacht_review_act3: "3",
        JobState.wacht_review_rs_gegevens: "rs-gegevens",
        JobState.wacht_review_rs_regels: "rs-regels",
    }[job.state]
    if feedback.activiteit != verwacht:
        raise HTTPException(status_code=400, detail=f"Feedback voor activiteit {verwacht} verwacht")
    schedule(get_engine().apply_feedback(project_id, feedback))
    # State/ronde zijn de pre-transitie-waarden; de overgang draait async.
    return FeedbackAccepted(id=project_id, state=job.state, ronde=job.current_ronde)


@router.post("/{project_id}/retry", status_code=status.HTTP_202_ACCEPTED, response_model=CreateAccepted)
async def retry_project(project_id: str, client_id: str = Depends(rate_limited_client)):
    store = get_store()
    p = await _project_or_404(store, project_id, client_id)
    if p.state != JobState.fout:
        raise HTTPException(status_code=409, detail=f"Retry alleen vanuit fout; nu: {p.state}")
    schedule(get_engine().retry(project_id))
    return CreateAccepted(id=project_id, naam=p.naam, state=JobState.queued)


@router.get("/{project_id}/rapport", response_model=Rapport)
async def project_rapport(project_id: str, client_id: str = Depends(require_client)):
    store = get_store()
    await _project_or_404(store, project_id, client_id)
    data = await store.lees_rapport(project_id)
    if data is None:
        raise HTTPException(status_code=409, detail="Rapport nog niet gereed")
    return data


@router.get("/{project_id}/rapport.md", response_class=PlainTextResponse)
async def project_rapport_md(project_id: str, client_id: str = Depends(require_client)):
    store = get_store()
    await _project_or_404(store, project_id, client_id)
    data = await store.lees_rapport(project_id)
    if data is None:
        raise HTTPException(status_code=409, detail="Rapport nog niet gereed")
    from ..markdown import rapport_naar_markdown
    return rapport_naar_markdown(data)


@router.get("/{project_id}/ronde/{activiteit}/{ronde}")
async def project_ronde(
    project_id: str, activiteit: str, ronde: int, client_id: str = Depends(require_client)
):
    if activiteit not in ACTIVITEIT_CODES:
        raise HTTPException(
            status_code=400, detail=f"activiteit moet een van {ACTIVITEIT_CODES} zijn"
        )
    store = get_store()
    await _project_or_404(store, project_id, client_id)
    data = await store.lees_analyse(project_id, activiteit, ronde)
    if data is None:
        raise HTTPException(status_code=404, detail="Geen analyse voor deze ronde")
    return data


# --- Activiteit 3 alsnog (on-demand op een act2-only-afgeronde analyse) -------

@router.post("/{project_id}/act3", status_code=status.HTTP_202_ACCEPTED,
             response_model=CreateAccepted)
async def start_act3(project_id: str, client_id: str = Depends(rate_limited_client)):
    """Voer activiteit 3 alsnog uit op een analyse die met "akkoord-afronden" na activiteit 2
    is afgerond. Geen body: de review-instelling erft van de analyse zelf (`job.review`)."""
    store = get_store()
    p = await _project_or_404(store, project_id, client_id)
    if p.state != JobState.klaar:
        raise HTTPException(
            status_code=409,
            detail=f"Activiteit 3 start alleen vanuit een afgeronde analyse (klaar); nu: {p.state}",
        )
    if p.scope != "act2":
        raise HTTPException(
            status_code=409,
            detail="Activiteit 3 is al uitgevoerd voor deze analyse.",
        )
    # Claim synchroon (klaar → act3_runt) vóór de 202 — zelfde motivatie als bij regelspraak.
    engine = get_engine()
    job = await engine.claim_act3(project_id)
    if job is None:
        raise HTTPException(
            status_code=409,
            detail="Activiteit 3 is al gestart of de analyse is niet meer `klaar`.",
        )
    schedule(engine.run_act3_fase(job))
    return CreateAccepted(id=project_id, naam=p.naam, state=job.state)


# --- RegelSpraak-vervolgfase (on-demand op een afgeronde analyse) -------------

@router.post("/{project_id}/regelspraak", status_code=status.HTTP_202_ACCEPTED,
             response_model=CreateAccepted)
async def start_regelspraak(
    project_id: str, body: RegelspraakStart | None = None,
    client_id: str = Depends(rate_limited_client),
):
    store = get_store()
    p = await _project_or_404(store, project_id, client_id)
    if p.state != JobState.klaar:
        raise HTTPException(
            status_code=409,
            detail=f"RegelSpraak start alleen vanuit een afgeronde analyse (klaar); nu: {p.state}",
        )
    if p.scope == "act2":
        raise HTTPException(
            status_code=409,
            detail="Deze analyse is afgerond zonder activiteit 3 (geen begrippen/afleidingsregels "
                   "om te formaliseren); voer eerst activiteit 3 uit.",
        )
    review = body.review if body is not None else None
    # Claim synchroon (klaar → rs_gegevens_runt) vóór de 202: zo is de DB al niet-terminaal en kan
    # de heropende events-stream niet meteen `done` krijgen; een verloren race (dubbele POST) geeft
    # een eerlijke 409 i.p.v. een optimistische false-202.
    engine = get_engine()
    job = await engine.claim_regelspraak(project_id, review)
    if job is None:
        raise HTTPException(
            status_code=409,
            detail="RegelSpraak-fase is al gestart of de analyse is niet meer `klaar`.",
        )
    schedule(engine.run_regelspraak_fase(job))
    return CreateAccepted(id=project_id, naam=p.naam, state=job.state)


@router.get("/{project_id}/regelspraak", response_model=RegelspraakModel)
async def project_regelspraak(project_id: str, client_id: str = Depends(require_client)):
    store = get_store()
    await _project_or_404(store, project_id, client_id)
    data = await store.lees_regelspraak(project_id)
    if data is None:
        raise HTTPException(status_code=409, detail="RegelSpraak-model nog niet gereed")
    return data


@router.get("/{project_id}/regelspraak.rs", response_class=PlainTextResponse)
async def project_regelspraak_rs(project_id: str, client_id: str = Depends(require_client)):
    store = get_store()
    await _project_or_404(store, project_id, client_id)
    data = await store.lees_regelspraak(project_id)
    if data is None:
        raise HTTPException(status_code=409, detail="RegelSpraak-model nog niet gereed")
    from ..engine.render_regelspraak import render_rs
    return render_rs(data)


@router.get("/{project_id}/regelspraak.md", response_class=PlainTextResponse)
async def project_regelspraak_md(project_id: str, client_id: str = Depends(require_client)):
    store = get_store()
    await _project_or_404(store, project_id, client_id)
    data = await store.lees_regelspraak(project_id)
    if data is None:
        raise HTTPException(status_code=409, detail="RegelSpraak-model nog niet gereed")
    from ..engine.render_regelspraak import render_md
    return render_md(data)


@router.get("/{project_id}/events")
async def project_events(project_id: str, request: Request, client_id: str = Depends(require_client)):
    """SSE — stuurt state-updates totdat het project klaar of in fout is (max 10 minuten)."""
    store = get_store()
    await _project_or_404(store, project_id, client_id)

    async def stream():
        seen = None
        for _ in range(120):
            if await request.is_disconnected():
                return  # client weg → stop met pollen i.p.v. 10 min doorgaan
            p = await store.load_project(project_id)
            if p is None:
                yield "event: error\ndata: project niet gevonden\n\n"
                return
            current = {
                "state": p.state,
                "current_activiteit": p.current_activiteit,
                "current_ronde": p.current_ronde,
                "current_fase": p.current_fase,
            }
            if current != seen:
                yield f"data: {json.dumps(current)}\n\n"
                seen = current
            else:
                # Heartbeat: zie alle_project_events — voorkomt body-timeout in de BFF bij stille polls.
                yield ": keep-alive\n\n"
            if p.state in TERMINAL_STATES:
                yield "event: done\ndata: {}\n\n"
                return
            await asyncio.sleep(5)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
