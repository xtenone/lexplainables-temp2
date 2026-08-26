"""Async SQLAlchemy-Core laag: engine-beheer + tabeldefinities.

De datalaag is bewust **Core** (geen ORM): alle SQL is geïsoleerd in de store en de service-
modules (profiles/wetten/usage), de domeinmodellen blijven plain Pydantic. De types zijn
portable — `JSON` wordt `JSONB` op PostgreSQL en gewone `JSON` op SQLite, zodat de unit-tests
op een in-memory SQLite draaien en productie op PostgreSQL (CloudNativePG).

De engine wordt lui geïnitialiseerd (lifespan in productie, fixture in tests) zodat de store
zonder verbinding importeerbaar blijft.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    inspect,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

# JSONB op Postgres (indexeerbaar, efficiënt), gewone JSON op SQLite (tests).
_JSON = JSON().with_variant(JSONB(), "postgresql")
# Tijdzone-bewust opslaan; op Postgres = timestamptz. SQLite kent geen tz → normaliseer bij lezen
# (zie aware()), zodat .isoformat() altijd een offset (UTC) draagt.
_DT = DateTime(timezone=True)

metadata = MetaData()

# Eén rij per analyse-project: state-machine-velden (typed) + JSON voor de samengestelde velden.
# rondes/feedback staan in een aparte tabel (ronde-immutabiliteit, gerichte writes); het
# eindrapport zit als JSON-kolom op het project.
projects = Table(
    "projects",
    metadata,
    Column("slug", String(255), primary_key=True),
    Column("naam", Text, nullable=False, default=""),
    Column("omschrijving", Text, nullable=False, default=""),
    # Het werkgebied bevat meerdere bronnen: list[{bwbId, artikel, lid}] als JSON.
    Column("bronnen", _JSON, nullable=False, default=list),
    Column("analysefocus", Text, nullable=False, default=""),
    # Aangeleverde bestaande begrippenlijst (suggestieve act-3-invoer): list[BegripInvoer] als JSON.
    Column("begrippenlijst", _JSON, nullable=False, default=list),
    Column("review", Boolean, nullable=False, default=True),
    Column("model_profile", String(128), nullable=False, default=""),
    Column("client_id", String(128), nullable=False, default=""),
    Column("state", String(32), nullable=False),
    # Analyse-omvang: "volledig" of "act2" (bewust afgerond zonder activiteit 3).
    Column("scope", String(16), nullable=False, default="volledig"),
    # Ruim genoeg voor de regelspraak-codes ("rs-gegevens"/"rs-regels") náást "2"/"3".
    Column("current_activiteit", String(16), nullable=True),
    Column("current_ronde", Integer, nullable=False, default=0),
    Column("current_fase", String(64), nullable=True),
    Column("current_fase_sinds", _DT, nullable=True),
    Column("waarschuwingen", _JSON, nullable=False, default=list),
    Column("error", _JSON, nullable=True),
    Column("provenance", _JSON, nullable=False, default=list),
    # Concurrency-claim: alleen door claim()/verleng_lease() beheerd (nooit via save_job).
    Column("owner", String(128), nullable=True),
    Column("lease_until", _DT, nullable=True),
    Column("created", _DT, nullable=False),
    Column("updated", _DT, nullable=False),
    Column("rapport", _JSON, nullable=True),
    # RegelSpraak-vervolgfase: het eind-model.json + of die fase met review draait.
    Column("regelspraak", _JSON, nullable=True),
    Column("regelspraak_review", Boolean, nullable=True),
    # Hot-path indexen: list_projects filtert op client_id + sorteert op updated DESC;
    # reaper/quota scannen op state. Zonder deze is dat een seq scan zodra de tabel groeit.
    Index("ix_projects_client_id_updated", "client_id", "updated"),
    Index("ix_projects_state", "state"),
)

# Immutabele analyse-ronde per (project, activiteit, ronde) + de bijbehorende review-feedback.
rondes = Table(
    "rondes",
    metadata,
    Column("project_slug", String(255), nullable=False),
    Column("activiteit", String(16), nullable=False),
    Column("ronde", Integer, nullable=False),
    Column("analyse", _JSON, nullable=False, default=dict),
    Column("feedback", _JSON, nullable=True),
    PrimaryKeyConstraint("project_slug", "activiteit", "ronde"),
)

llm_profiles = Table(
    "llm_profiles",
    metadata,
    Column("name", String(128), primary_key=True),
    Column("provider", String(64), nullable=False, default="azure_ai"),
    Column("model", String(128), nullable=False, default=""),
    Column("api_base", String(512), nullable=False, default=""),
    Column("api_version", String(64), nullable=True),
    Column("output_strategy", String(64), nullable=False, default="prompt_and_parse"),
    Column("temperature", Float, nullable=False, default=0.0),
    Column("enc_api_key", Text, nullable=True),
    Column("is_default", Boolean, nullable=False, default=False),
    Column("updated_by", String(128), nullable=False, default=""),
    Column("created", _DT, nullable=False),
    Column("updated", _DT, nullable=False),
)

wet_catalogus = Table(
    "wet_catalogus",
    metadata,
    Column("bwbId", String(64), primary_key=True),
    Column("naam", Text, nullable=False, default=""),
    Column("updated_by", String(128), nullable=False, default=""),
    Column("created", _DT, nullable=False),
    Column("updated", _DT, nullable=False),
)

# Login-accounts voor de webapp. De API is de identiteitsbron; de frontend (Auth.js) houdt alleen
# de browsersessie. Inloggen gaat met de `userid` (de natuurlijke sleutel, lowercase genormaliseerd);
# `email` is een verplicht, uniek registratiegegeven (geen inlog-identiteit). Het TOTP-secret staat
# versleuteld (Fernet, zie secrets_crypto) en is optioneel (2FA staat standaard uit).
users = Table(
    "users",
    metadata,
    Column("userid", String(64), primary_key=True),
    Column("email", String(320), nullable=False, unique=True),
    Column("password_hash", Text, nullable=False),
    Column("role", String(16), nullable=False, default="analist"),
    Column("totp_secret_enc", Text, nullable=True),
    Column("totp_enabled", Boolean, nullable=False, default=False),
    Column("active", Boolean, nullable=False, default=True),
    Column("created", _DT, nullable=False),
    Column("updated", _DT, nullable=False),
)

# Genereerbare API-tokens voor programmatische admin-toegang (bv. de admin-MCP), náást de
# statische env-admin-tokens. Alleen de sha256-HASH van het token wordt bewaard (hoog-entropie →
# geen bcrypt nodig); de plaintext wordt één keer bij aanmaken getoond en nergens opgeslagen. Het
# `token_prefix` dient enkel voor herkenning in de UI. Intrekken = `active=False` (geen delete-eis).
api_tokens = Table(
    "api_tokens",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("label", String(128), nullable=False, default=""),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("token_prefix", String(24), nullable=False, default=""),
    Column("scope", String(16), nullable=False, default="admin"),
    Column("active", Boolean, nullable=False, default=True),
    Column("created_by", String(128), nullable=False, default=""),
    Column("created", _DT, nullable=False),
    Column("last_used", _DT, nullable=True),
)

# Generieke runtime-config (key/value) — beheerbaar via /v1/admin/settings + /beheer. Eerste
# sleutel: `capture_llm_calls` (bool). Bewust een aparte, kleine tabel zodat een toggle de hot
# projects-rij niet raakt en latere instellingen er zonder migratie bij kunnen.
app_settings = Table(
    "app_settings",
    metadata,
    Column("key", String(64), primary_key=True),
    Column("value", _JSON, nullable=True),
    Column("updated", _DT, nullable=False),
)

# Eén rij per feitelijke LLM-call (incl. auto-correctie-herhalingen, de verwijzing-inventaris en
# gefaalde pogingen). Legt de letterlijke prompt + ruwe respons vast voor prompt-/gedragsanalyse.
# Apart van `rondes` (die alleen het uiteindelijke ronde-resultaat bewaart) en standaard leeg —
# capture staat default uit (app_settings.capture_llm_calls).
llm_calls = Table(
    "llm_calls",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("project_slug", String(255), nullable=False),
    Column("activiteit", String(16), nullable=False, default=""),
    Column("ronde", Integer, nullable=False, default=0),
    Column("poging", Integer, nullable=False, default=1),
    Column("fase", String(32), nullable=False, default=""),
    Column("model", String(128), nullable=False, default=""),
    Column("provider", String(64), nullable=False, default=""),
    Column("system_prompt", Text, nullable=False, default=""),
    Column("user_prompt", Text, nullable=False, default=""),
    Column("response_text", Text, nullable=False, default=""),
    Column("tokens_in", Integer, nullable=False, default=0),
    Column("tokens_out", Integer, nullable=False, default=0),
    Column("ok", Boolean, nullable=False, default=True),
    Column("error", Text, nullable=True),
    Column("tijdstip", _DT, nullable=False),
    Index("ix_llm_calls_project_slug_id", "project_slug", "id"),
)

# --- Annotatie-domein (wetsanalyse-workbench) ---------------------------------
# Vers domein, los van de analyse-tabellen. Eén rij per bron-document; de elementen (met hun
# review-levenscyclus + beslissingen) staan als JSON — het document draagt de HUIDIGE staat.
annotatie_documenten = Table(
    "annotatie_documenten",
    metadata,
    Column("slug", String(255), primary_key=True),
    Column("client_id", String(128), nullable=False, default=""),
    Column("werkgebied", Text, nullable=False, default=""),
    Column("bwbId", String(64), nullable=False, default=""),
    Column("artikel", String(32), nullable=False, default=""),
    Column("lid", String(32), nullable=False, default=""),
    Column("status", String(24), nullable=False, default="in_review"),
    Column("elementen", _JSON, nullable=False, default=list),
    Column("created", _DT, nullable=False),
    Column("updated", _DT, nullable=False),
    Index("ix_annotatie_docs_client_updated", "client_id", "updated"),
)

# Append-only audit trail: de onwijzigbare geschiedenis (event-log) náást de huidige documentstaat.
# Alleen inserts; nooit update/delete. De tijdlijn = ORDER BY id.
annotatie_audit = Table(
    "annotatie_audit",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("document_slug", String(255), nullable=False),
    Column("client_id", String(128), nullable=False, default=""),
    Column("actor", String(128), nullable=False, default=""),
    Column("actie", String(64), nullable=False, default=""),
    Column("element_id", String(64), nullable=True),
    Column("detail", _JSON, nullable=True),
    Column("tijdstip", _DT, nullable=False),
    Index("ix_annotatie_audit_doc_id", "document_slug", "id"),
)


# --- engine-beheer -------------------------------------------------------------

_engine: AsyncEngine | None = None


def init_engine(url: str, **kwargs) -> AsyncEngine:
    """(Her)initialiseer de globale async engine. Een in-memory SQLite-URL krijgt automatisch een
    StaticPool zodat alle verbindingen dezelfde database delen (anders is elke connectie leeg)."""
    global _engine
    # Normaliseer een kale Postgres-URL naar de async-driver. Zo is de connection-string die de
    # CloudNativePG-operator genereert (`postgresql://…`) rechtstreeks bruikbaar als DATABASE_URL.
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    elif url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    is_sqlite_mem = url.startswith("sqlite") and (":memory:" in url or url.endswith("://"))
    if is_sqlite_mem:
        kwargs.setdefault("poolclass", StaticPool)
        kwargs.setdefault("connect_args", {"check_same_thread": False})
    elif not url.startswith("sqlite"):
        kwargs.setdefault("pool_pre_ping", True)
    _engine = create_async_engine(url, **kwargs)
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("DB-engine niet geïnitialiseerd (roep db.init_engine aan in de lifespan).")
    return _engine


async def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def create_all() -> None:
    """Maak de tabellen aan (tests + beproevingsfase; productie kan dit later via Alembic doen)."""
    async with get_engine().begin() as conn:
        await conn.run_sync(metadata.create_all)


async def reconcile_schema() -> None:
    """Idempotente schema-bijwerking voor de werkgebied/bronnen-overgang.

    `create_all` maakt alleen ONTBREKENDE tabellen; het migreert geen kolommen van een
    bestaande tabel. De `projects`-tabel ging van scalar `bwbId/artikel/lid` naar één
    `bronnen` JSON-kolom. Bij een bestaande tabel (zonder Alembic) brengen we het schema hier
    in lijn: voeg `bronnen` toe en laat de legacy-kolommen vallen. Veilig, want er is geen
    data om te bewaren; op een verse DB (kolom al aanwezig) is dit een no-op."""
    engine = get_engine()

    def _kolommen(sync_conn):
        insp = inspect(sync_conn)
        if not insp.has_table("projects"):
            return None
        return {c["name"] for c in insp.get_columns("projects")}

    async with engine.begin() as conn:
        bestaande = await conn.run_sync(_kolommen)
        if bestaande is None:
            return  # tabel bestaat (nog) niet; create_all maakt 'm met het juiste schema
        is_pg = engine.url.get_backend_name() == "postgresql"
        if "bronnen" not in bestaande:
            typ = "JSONB" if is_pg else "JSON"
            default = "'[]'::jsonb" if is_pg else "'[]'"
            await conn.exec_driver_sql(
                f"ALTER TABLE projects ADD COLUMN bronnen {typ} NOT NULL DEFAULT {default}"
            )
        # Legacy scalar-kolommen opruimen (case-sensitief → quoten).
        for legacy in ("bwbId", "artikel", "lid"):
            if legacy in bestaande:
                await conn.exec_driver_sql(f'ALTER TABLE projects DROP COLUMN "{legacy}"')
        # RegelSpraak-vervolgfase: kolommen op een bestaande tabel idempotent toevoegen.
        if "regelspraak" not in bestaande:
            typ = "JSONB" if is_pg else "JSON"
            await conn.exec_driver_sql(f"ALTER TABLE projects ADD COLUMN regelspraak {typ}")
        if "regelspraak_review" not in bestaande:
            await conn.exec_driver_sql("ALTER TABLE projects ADD COLUMN regelspraak_review BOOLEAN")
        # Aangeleverde begrippenlijst: idempotent toevoegen; bestaande rijen = lege lijst.
        if "begrippenlijst" not in bestaande:
            typ = "JSONB" if is_pg else "JSON"
            default = "'[]'::jsonb" if is_pg else "'[]'"
            await conn.exec_driver_sql(
                f"ALTER TABLE projects ADD COLUMN begrippenlijst {typ} NOT NULL DEFAULT {default}"
            )
        # Analyse-omvang ("volledig"/"act2"): idempotent toevoegen; bestaande rijen = volledig.
        if "scope" not in bestaande:
            await conn.exec_driver_sql(
                "ALTER TABLE projects ADD COLUMN scope VARCHAR(16) NOT NULL DEFAULT 'volledig'"
            )
        # current_activiteit/rondes.activiteit verbreed (rs-codes). Alleen op Postgres relevant —
        # SQLite handhaaft de VARCHAR-lengte niet. **Echt idempotent**: alleen ALTER-en als de kolom
        # nog niet ≥16 is. Een onvoorwaardelijke ALTER TYPE botst met een view die van de kolom
        # afhangt (bv. Grafana's `dashboard_jobs`) → "cannot alter type of a column used by a view"
        # → startup-crash. Skippen zodra de breedte al klopt vermijdt die view-afhankelijkheid.
        if is_pg:
            async def _verbreed_indien_nodig(tabel: str, kolom: str) -> None:
                res = await conn.exec_driver_sql(
                    "SELECT character_maximum_length FROM information_schema.columns "
                    f"WHERE table_name = '{tabel}' AND column_name = '{kolom}'"
                )
                rij = res.first()
                huidige = rij[0] if rij else None
                if huidige is not None and huidige < 16:
                    await conn.exec_driver_sql(
                        f"ALTER TABLE {tabel} ALTER COLUMN {kolom} TYPE VARCHAR(16)"
                    )

            await _verbreed_indien_nodig("projects", "current_activiteit")
            await _verbreed_indien_nodig("rondes", "activiteit")
        # Hot-path indexen op een bestaande tabel: create_all maakt indexen alleen mee bij een
        # verse tabel, dus voor een bestaande prod-DB hier idempotent toevoegen. IF NOT EXISTS
        # werkt op zowel PostgreSQL als SQLite, dus ook veilig ná create_all in de tests.
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_projects_client_id_updated "
            "ON projects (client_id, updated)"
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_projects_state ON projects (state)"
        )


def aware(dt: datetime | None) -> datetime | None:
    """Normaliseer een uit de DB gelezen datetime naar UTC-aware. SQLite geeft naïeve datetimes
    terug (geen tz-opslag); Postgres geeft al aware terug. Zo serialiseert .isoformat() altijd met
    offset en leest de browser de tijd niet als lokale tijd."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
