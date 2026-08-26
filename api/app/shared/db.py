"""Async SQLAlchemy-Core laag: gedeelde `metadata` + engine-beheer.

De datalaag is bewust **Core** (geen ORM): alle SQL is geïsoleerd in de store-modules per feature,
de domeinmodellen blijven plain Pydantic. De tabeldefinities zelf staan niet hier maar in het
`models.py` van de feature die ze bezit (werkwijze-ADR-0011, "de ene bron") — dit bestand draagt
alleen de gedeelde `MetaData`-instantie waarop elke feature zijn `Table` registreert, zodat
`create_all`/`reconcile_schema` alle tabellen in één keer zien. Types zijn portable — `JSON` wordt
`JSONB` op PostgreSQL en gewone `JSON` op SQLite, zodat de unit-tests op een in-memory SQLite draaien
en productie op PostgreSQL.

De engine wordt lui geïnitialiseerd (lifespan in productie, fixture in tests) zodat de modules
zonder verbinding importeerbaar blijven.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, MetaData, Table, text
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

# JSONB op Postgres (indexeerbaar, efficiënt), gewone JSON op SQLite (tests). Elke feature die een
# JSON-kolom nodig heeft importeert dit type i.p.v. een eigen variant te bouwen.
JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")
# Tijdzone-bewust opslaan; op Postgres = timestamptz. SQLite kent geen tz → normaliseer bij lezen
# (zie aware()), zodat .isoformat() altijd een offset (UTC) draagt.
DATETIME_TZ = DateTime(timezone=True)

# Gedeelde MetaData — elke feature registreert zijn eigen Table(s) hierop via `from ...shared.db
# import metadata` in zijn `models.py`. NB: de analyse-pijplijn en de wet-catalogus zijn verwijderd;
# de bijbehorende tabellen (`projects`, `rondes`, `llm_calls`, `app_settings`, `wet_catalogus`)
# worden niet meer gedefinieerd of aangemaakt — op een bestaande productie-DB blijven ze verweesd
# staan; het daadwerkelijk droppen is een aparte, bewuste migratie.
metadata = MetaData()


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
    """Maak de tabellen aan (tests + beproevingsfase; productie kan dit later via Alembic doen).
    Idempotent: alleen ontbrekende tabellen worden aangemaakt. Vereist dat alle feature-`models.py`-
    modules al geïmporteerd zijn (main.py doet dat via de router-imports) zodat hun `Table`s op
    `metadata` geregistreerd staan."""
    async with get_engine().begin() as conn:
        await conn.run_sync(metadata.create_all)


def _ontbrekende_kolommen(sync_conn, tabel: Table) -> list[Column]:
    """Kolommen die in de definitie staan maar (nog) niet in de DB. Lege lijst als de tabel ontbreekt
    (die maakt `create_all` compleet aan)."""
    insp = sa_inspect(sync_conn)
    if not insp.has_table(tabel.name):
        return []
    bestaand = {c["name"] for c in insp.get_columns(tabel.name)}
    return [col for col in tabel.columns if col.name not in bestaand]


async def reconcile_schema() -> None:
    """Additieve kolom-migratie: voeg kolommen toe die in de tabeldefinitie staan maar in de DB
    ontbreken. `create_all` maakt alleen ontbrekende *tabellen*; zonder deze stap breekt een `SELECT`
    over een nieuw gedefinieerde kolom op een bestaande productie-tabel. **Alleen toevoegen** — nooit
    droppen of typewijzigen (dus dataverlies uitgesloten). Veilig op SQLite én Postgres; draait in de
    lifespan vóór het serveren."""
    engine = get_engine()
    preparer = engine.dialect.identifier_preparer
    async with engine.begin() as conn:
        for tabel in metadata.tables.values():
            for col in await conn.run_sync(_ontbrekende_kolommen, tabel):
                coltype = col.type.compile(dialect=engine.dialect)
                ddl = (
                    f"ALTER TABLE {preparer.format_table(tabel)} "
                    f"ADD COLUMN {preparer.format_column(col)} {coltype}"
                )
                await conn.execute(text(ddl))


def aware(dt: datetime | None) -> datetime | None:
    """Normaliseer een uit de DB gelezen datetime naar UTC-aware. SQLite geeft naïeve datetimes
    terug (geen tz-opslag); Postgres geeft al aware terug. Zo serialiseert .isoformat() altijd met
    offset en leest de browser de tijd niet als lokale tijd."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
