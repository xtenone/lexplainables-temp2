"""Configuratie voor de BWB-import, geladen uit omgeving/.env.

Geen globale state: ``Settings.from_env()`` bouwt een onveranderlijk
configuratie-object dat expliciet wordt doorgegeven aan de componenten.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .rdf_vocab import DEFAULT_BASE_IRI, DEFAULT_ONTOLOGY_IRI

# Wortel van het project (bwb-import/), onafhankelijk van de werkdirectory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Officiële endpoints van het Basiswettenbestand (geverifieerd).
DEFAULT_SRU_BASE_URL = "https://zoekservice.overheid.nl/sru/Search"
DEFAULT_REPO_BASE_URL = "https://repository.officiele-overheidspublicaties.nl"


def _as_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "ja", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    """Onveranderlijke runtime-configuratie."""

    data_dir: Path
    schemas_dir: Path
    default_bwb_id: str
    sru_base_url: str
    repo_base_url: str
    validate_xsd: bool
    detect_tekstuele_refs: bool
    import_wti: bool
    service_api_key: str | None
    graphdb_url: str
    graphdb_repository: str
    graphdb_user: str | None
    graphdb_password: str | None
    graphdb_base_iri: str
    graphdb_ontology_iri: str

    @classmethod
    def from_env(cls, *, env_file: Path | None = None) -> Settings:
        """Laad instellingen uit ``.env`` (indien aanwezig) en omgeving."""
        load_dotenv(dotenv_path=env_file or (PROJECT_ROOT / ".env"))

        data_dir = Path(os.getenv("BWB_DATA_DIR", str(PROJECT_ROOT / "data")))
        schemas_dir = Path(os.getenv("BWB_SCHEMAS_DIR", str(PROJECT_ROOT / "schemas")))
        api_key = os.getenv("BWB_SERVICE_API_KEY") or None

        return cls(
            data_dir=data_dir,
            schemas_dir=schemas_dir,
            default_bwb_id=os.getenv("BWB_DEFAULT_ID", "BWBR0004770"),
            sru_base_url=os.getenv("BWB_SRU_URL", DEFAULT_SRU_BASE_URL),
            repo_base_url=os.getenv("BWB_REPO_URL", DEFAULT_REPO_BASE_URL),
            validate_xsd=_as_bool(os.getenv("BWB_VALIDATE_XSD"), default=True),
            detect_tekstuele_refs=_as_bool(os.getenv("BWB_DETECT_TEKSTUELE_REFS"), default=True),
            import_wti=_as_bool(os.getenv("BWB_IMPORT_WTI"), default=False),
            service_api_key=api_key,
            graphdb_url=os.getenv("GRAPHDB_URL", "http://graphdb:7200"),
            graphdb_repository=os.getenv("GRAPHDB_REPOSITORY", "inning"),
            graphdb_user=os.getenv("GRAPHDB_USER") or None,
            graphdb_password=os.getenv("GRAPHDB_PASSWORD") or None,
            graphdb_base_iri=os.getenv("GRAPHDB_BASE_IRI", DEFAULT_BASE_IRI),
            graphdb_ontology_iri=os.getenv("GRAPHDB_ONTOLOGY_IRI", DEFAULT_ONTOLOGY_IRI),
        )
