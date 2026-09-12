"""Alembic environment.

Runs SYNCHRONOUSLY even though the application is async. That is deliberate and
it is free: psycopg 3 provides both a sync and an async driver behind one URL
scheme, so `postgresql+psycopg://...` works for both. Migrations get the simpler
execution model — no event loop, no async template — against the identical
connection string. This is the main practical reason we chose psycopg over
asyncpg (see docs/decisions/0003).

The URL comes from the environment, never from alembic.ini, so no credential is
ever committed. On Neon, point DATABASE_MIGRATION_URL at the DIRECT (unpooled)
endpoint: migrations through a transaction-mode pooler misbehave. On Railway,
DATABASE_URL is correct for both.
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import get_settings

# Importing the models registers them on Base.metadata, which is what
# autogenerate compares the live database against.
from app.infrastructure.database import models  # noqa: F401
from app.infrastructure.database.base import Base
from app.infrastructure.database.engine import sync_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """Resolve the migration URL, preferring an explicit override."""
    explicit = os.getenv("DATABASE_MIGRATION_URL") or os.getenv("DATABASE_URL")
    url = explicit or get_settings().effective_migration_url
    if not url:
        raise RuntimeError(
            "No database URL. Set DATABASE_URL (or DATABASE_MIGRATION_URL) "
            "before running migrations."
        )
    return sync_database_url(url)


def run_migrations_offline() -> None:
    """Emit SQL without connecting.

    `alembic upgrade head --sql` uses this. Useful for reviewing exactly what a
    migration will do before it touches a production database.
    """
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect and apply migrations."""
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Autogenerate misses these unless asked. Both have bitten people.
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
