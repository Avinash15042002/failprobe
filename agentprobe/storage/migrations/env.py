"""Alembic migration environment (async).

Imports ``Base`` from ``agentprobe.storage.models`` so autogenerate and the
online migration runner have real metadata to work against. The database URL
is resolved at runtime from ``AGENTPROBE_DB_URL`` (falling back to
``ProbeConfig.db_url``) — the same precedence used by the runtime engine in
``db.py`` — so ``alembic upgrade head`` targets the configured database.
"""

from __future__ import annotations

import asyncio
import os

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from agentprobe.config import get_config
from agentprobe.storage.models import Base

# Alembic Config object, providing access to values within alembic.ini.
config = context.config

target_metadata = Base.metadata


def _resolve_db_url() -> str:
    """Resolve the database URL (env var first, then ``ProbeConfig.db_url``)."""
    return os.environ.get("AGENTPROBE_DB_URL") or get_config().db_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a live connection)."""
    context.configure(
        url=_resolve_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    """Configure the Alembic context against a live connection and migrate."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations within it."""
    connectable = async_engine_from_config(
        {"sqlalchemy.url": _resolve_db_url()},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode via the async engine."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
