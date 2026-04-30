"""Alembic environment for Hokusai application schema.

Uses ``hokusai_alembic_version`` as the version table so it does not collide
with MLflow's own ``alembic_version`` table in the same database. Reads the
target database URL from the ``DATABASE_URL`` environment variable.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

VERSION_TABLE = "hokusai_alembic_version"

target_metadata = None


def _resolve_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL must be set for alembic migrations (got empty value).")
    return url


def run_migrations_offline() -> None:
    """Run migrations in offline mode, emitting SQL to stdout."""
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in online mode using a real DB connection."""
    config.set_main_option("sqlalchemy.url", _resolve_url())
    section = config.get_section(config.config_ini_section, {})
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table=VERSION_TABLE,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
