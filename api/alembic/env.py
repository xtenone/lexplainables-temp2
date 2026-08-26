"""Alembic-omgeving voor de api-service (werkwijze-ADR-0005).

Eén migratiehistorie voor deze service. Het doelschema (`target_metadata`) is de gedeelde
`shared.db.metadata` waarop elke feature zijn `Table`(s) registreert (zie
`docs/project/architectuur/stack-profiel.md` §De ene bron) — er is geen apart, met de hand
bijgehouden schemabestand om synchroon te houden met de migraties. Importeer hier elke feature
se `models`-module zodat zijn tabellen vóór autogenerate/`run_migrations` geregistreerd zijn.

Migraties draaien synchroon (het gebruikelijke Alembic-patroon, ook als de app zelf async is via
asyncpg): `DATABASE_URL_SYNC` gebruikt daarom een sync-driver (`postgresql://…`, psycopg2), los
van de async `DATABASE_URL` van de app zelf.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Importeren registreert elke feature se Table(s) op shared.db.metadata (bijwerking van de
# module-level `Table(..., metadata, ...)`-aanroepen in elke models.py). Nieuw feature? Voeg hier
# zijn import toe.
from app.features.annotatie import models as _annotatie_models  # noqa: E402,F401
from app.features.api_tokens import models as _api_tokens_models  # noqa: E402,F401
from app.features.berichten import models as _berichten_models  # noqa: E402,F401
from app.features.feedback import models as _feedback_models  # noqa: E402,F401
from app.features.gesprekken import models as _gesprekken_models  # noqa: E402,F401
from app.features.identiteit_toegang import models as _identiteit_toegang_models  # noqa: E402,F401
from app.features.llm_profielen import models as _llm_profielen_models  # noqa: E402,F401
from app.shared.db import metadata as target_metadata  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.environ.get("DATABASE_URL_SYNC")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
