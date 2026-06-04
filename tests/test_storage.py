"""Tests for the FailProbe storage layer (ORM models + async DB engine).

Each test runs against a fresh temporary SQLite file. The engine/session
singletons in ``db`` are reset per test (private attributes are patched
directly, which is acceptable in tests) so isolation is guaranteed regardless
of test ordering.
"""

import pytest
from sqlalchemy import inspect, select

from failprobe.storage import db
from failprobe.storage.db import get_session, init_db
from failprobe.storage.models import (
    EvalResult,
    RegressionBaseline,
    Run,
    ToolCallRecord,
)

ALL_TABLES = {"runs", "tool_calls", "eval_results", "regression_baselines"}


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch) -> None:
    """Point storage at a fresh temp SQLite file and reset engine singletons."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("FAILPROBE_DB_URL", f"sqlite+aiosqlite:///{db_file.as_posix()}")
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_session_factory", None)


def test_models_have_expected_columns() -> None:
    """All four ORM models expose exactly the columns required by the spec."""
    assert set(Run.__table__.columns.keys()) == {
        "id",
        "agent_name",
        "input_text",
        "output_text",
        "duration_ms",
        "tokens_used",
        "model",
        "success",
        "failure_type",
        "failure_msg",
        "exception",
        "tags",
        "created_at",
    }
    assert set(ToolCallRecord.__table__.columns.keys()) == {
        "id",
        "run_id",
        "tool_name",
        "params",
        "result",
        "duration_ms",
        "error",
        "timestamp",
    }
    assert set(EvalResult.__table__.columns.keys()) == {
        "id",
        "run_id",
        "judge_model",
        "score",
        "reasoning",
        "confidence",
        "human_label",
        "human_notes",
        "created_at",
    }
    assert set(RegressionBaseline.__table__.columns.keys()) == {
        "id",
        "name",
        "metrics",
        "n_runs",
        "created_at",
    }


def test_datetime_columns_are_timezone_aware() -> None:
    """All ``datetime`` columns are declared with ``timezone=True``."""
    assert Run.__table__.c.created_at.type.timezone is True
    assert ToolCallRecord.__table__.c.timestamp.type.timezone is True
    assert EvalResult.__table__.c.created_at.type.timezone is True
    assert RegressionBaseline.__table__.c.created_at.type.timezone is True


def test_foreign_keys_point_to_runs() -> None:
    """``tool_calls`` and ``eval_results`` reference ``runs.id``."""
    assert {fk.target_fullname for fk in ToolCallRecord.__table__.c.run_id.foreign_keys} == {
        "runs.id"
    }
    assert {fk.target_fullname for fk in EvalResult.__table__.c.run_id.foreign_keys} == {"runs.id"}


def test_default_db_url_is_sqlite(monkeypatch) -> None:
    """With no env override, the URL falls back to the SQLite config default."""
    monkeypatch.delenv("FAILPROBE_DB_URL", raising=False)
    assert db._resolve_db_url().startswith("sqlite")


def test_env_var_overrides_config(monkeypatch) -> None:
    """Setting FAILPROBE_DB_URL swaps the connection (e.g. to Postgres)."""
    monkeypatch.setenv("FAILPROBE_DB_URL", "postgresql+asyncpg://u:p@host/db")
    assert db._resolve_db_url() == "postgresql+asyncpg://u:p@host/db"


async def test_init_db_creates_all_tables() -> None:
    """``init_db()`` creates all four tables in a fresh SQLite file."""
    await init_db()
    engine = await db.get_engine(db._resolve_db_url())
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
    assert ALL_TABLES <= tables


async def test_init_db_is_idempotent() -> None:
    """Calling ``init_db()`` twice does not raise."""
    await init_db()
    await init_db()


async def test_get_session_roundtrip() -> None:
    """``get_session()`` yields a usable session; a Run can be written and read."""
    await init_db()
    async with get_session() as session:
        run = Run(
            agent_name="weather-agent",
            input_text='"What is the weather?"',
            output_text='"Sunny."',
            duration_ms=42.0,
            success=True,
            tags="{}",
        )
        session.add(run)
        await session.commit()
        run_id = run.id  # readable post-commit thanks to expire_on_commit=False

    assert run_id is not None
    async with get_session() as session:
        fetched = (await session.execute(select(Run).where(Run.id == run_id))).scalar_one()
        assert fetched.agent_name == "weather-agent"
        assert fetched.success is True
        assert fetched.created_at is not None
