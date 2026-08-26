"""FastAPI-service die de BWB-import via HTTP aanstuurt.

Endpoints:
- ``GET  /health``  -> eenvoudige liveness-check.
- ``POST /import``  -> importeer één regeling (``bwb_id``, default uit config)
  of een batch (``bwb_ids``); per wet idempotent, fouten per wet gerapporteerd.

De service publiceert bewust geen hostpoort: importeren is een schrijfactie op de
graaf en wordt van binnen het docker-netwerk aangeroepen. Optioneel beveiligd met
een ``X-API-Key``-header (``BWB_SERVICE_API_KEY``).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, model_validator

from app.config import Settings
from app.main import run_import, run_imports

logger = logging.getLogger(__name__)


class ImportRequest(BaseModel):
    """Aanvraag voor een import.

    ``bwb_ids`` (batch) heeft voorrang; anders ``bwb_id`` met fallback op de
    config-default.
    """

    bwb_id: str | None = None
    bwb_ids: list[str] | None = None

    @model_validator(mode="after")
    def _valideer(self) -> ImportRequest:
        if self.bwb_ids is not None and not self.bwb_ids:
            raise ValueError("bwb_ids mag niet leeg zijn")
        return self


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = app.state.settings = Settings.from_env()
    logger.info(
        "BWB-importservice gestart (GraphDB: %s/%s)",
        settings.graphdb_url,
        settings.graphdb_repository,
    )
    yield


app = FastAPI(title="BWB-import", version="0.1.0", lifespan=lifespan)


def _check_api_key(settings: Settings, provided: str | None) -> None:
    if settings.service_api_key and provided != settings.service_api_key:
        raise HTTPException(status_code=401, detail="Ongeldige of ontbrekende API-key")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/import")
async def importeer(
    body: ImportRequest | None = None,
    x_api_key: str | None = Header(default=None),
) -> dict:
    settings: Settings = app.state.settings
    _check_api_key(settings, x_api_key)

    # Batch: per-wet resultaat, een falende wet breekt de batch niet.
    if body is not None and body.bwb_ids is not None:
        logger.info("Batch-import-verzoek voor %d regelingen", len(body.bwb_ids))
        resultaten = await run_in_threadpool(run_imports, body.bwb_ids, settings)
        geslaagd = sum(1 for r in resultaten if r.ok)
        if geslaagd == len(resultaten):
            status = "ok"
        elif geslaagd:
            status = "gedeeltelijk"
        else:
            status = "mislukt"
        return {"status": status, "resultaten": [r.as_dict() for r in resultaten]}

    # Enkele wet: de bestaande (legacy) responsvorm blijft ongewijzigd.
    bwb_id = (body.bwb_id if body else None) or settings.default_bwb_id
    logger.info("Import-verzoek voor %s", bwb_id)
    try:
        summary = await run_in_threadpool(run_import, bwb_id, settings)
    except Exception as exc:  # noqa: BLE001 - geef nette HTTP-fout terug
        logger.error("Import mislukt voor %s: %s", bwb_id, exc)
        raise HTTPException(status_code=500, detail=f"Import mislukt: {exc}") from exc

    return {"status": "ok", "overzicht": summary.as_dict()}
