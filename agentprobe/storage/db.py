"""Async database engine factory and session management for AgentProbe.

Supports SQLite (dev, zero config) and PostgreSQL (prod) via a single
connection string. The string is resolved from the ``AGENTPROBE_DB_URL``
environment variable if set, otherwise from ``ProbeConfig.db_url`` (spec
§5.4 — "Connection string from ProbeConfig.db_url"). Swapping to Postgres
therefore requires only changing the env var.

The engine and session factory are module-level singletons created on first
use; ``get_session()`` and ``init_db()`` reuse them. This module contains no
business logic — only connection plumbing.
"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from agentprobe.config import get_config
from agentprobe.storage.models import Base

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _resolve_db_url() -> str:
    """Resolve the active database URL.

    Precedence: the ``AGENTPROBE_DB_URL`` environment variable, then
    ``ProbeConfig.db_url``. Returns the connection string passed to the async
    engine.
    """
    return os.environ.get("AGENTPROBE_DB_URL") or get_config().db_url


async def get_engine(db_url: str) -> AsyncEngine:
    """Return the process-wide async engine, creating it on first call.

    The engine is a module-level singleton: the ``db_url`` of the first call
    wins, and subsequent calls return the existing engine regardless of the
    argument. Also initializes the session factory with
    ``expire_on_commit=False`` (required for safe async access to attributes
    after commit).

    Args:
        db_url: SQLAlchemy async connection string used to create the engine.

    Returns:
        The shared :class:`AsyncEngine`.
    """
    global _engine, _session_factory
    if _engine is None:
        _engine = create_async_engine(db_url, echo=False)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an :class:`AsyncSession` bound to the shared engine.

    Use as an async context manager::

        async with get_session() as session:
            session.add(run)
            await session.commit()

    The engine and session factory are lazily initialized from the resolved
    database URL on first use.
    """
    await get_engine(_resolve_db_url())
    assert _session_factory is not None  # set as a side effect of get_engine
    async with _session_factory() as session:
        yield session


async def init_db() -> None:
    """Create all tables if they do not already exist.

    Idempotent — safe to call on every startup. Resolves the database URL,
    ensures the engine exists, and runs ``Base.metadata.create_all`` against
    it.
    """
    engine = await get_engine(_resolve_db_url())
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
