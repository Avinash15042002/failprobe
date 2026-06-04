"""Tests for the async span emitter (``failprobe/tracer.py``, Task 08).

Each acceptance criterion is covered: ``_emit_span`` returns without awaiting
storage, spans land in SQLite within ~100 ms, a DB-write failure is swallowed
while the worker keeps running, the console line is printed before the DB
write, and a burst of 50 spans is flushed in a single transaction.

Tests run against a fresh temp SQLite file per test. The tracer's module-level
worker state is reset per test so each runs on its own event loop in isolation.
"""

import asyncio

import pytest
from sqlalchemy import select

from failprobe import tracer
from failprobe.models import AgentSpan, ToolCall
from failprobe.storage import db
from failprobe.storage.db import get_session, init_db
from failprobe.storage.models import Run, ToolCallRecord


@pytest.fixture(autouse=True)
async def _fresh_env(tmp_path, monkeypatch) -> None:
    """Fresh temp DB + reset DB/tracer singletons, then create tables."""
    db_file = tmp_path / "tracer.db"
    monkeypatch.setenv("FAILPROBE_DB_URL", f"sqlite+aiosqlite:///{db_file.as_posix()}")
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_session_factory", None)
    monkeypatch.setattr(tracer, "_queue", asyncio.Queue())
    monkeypatch.setattr(tracer, "_worker_task", None)
    monkeypatch.setattr(tracer, "_worker_loop", None)
    await init_db()


def _span(run_id: str = "run-0001abcd", **kwargs) -> AgentSpan:
    """Build a minimal span with overridable fields."""
    defaults = dict(
        run_id=run_id,
        agent_name="test-agent",
        input="q",
        output="r",
        duration_ms=50.0,
    )
    defaults.update(kwargs)
    return AgentSpan(**defaults)


async def _count_runs() -> int:
    async with get_session() as session:
        rows = (await session.execute(select(Run))).scalars().all()
        return len(rows)


# --------------------------------------------------------------------------- #
# _emit_span returns immediately (does not await storage)
# --------------------------------------------------------------------------- #
async def test_emit_does_not_write_synchronously() -> None:
    """After ``_emit_span`` returns, nothing has been persisted yet."""
    await tracer._emit_span(_span())
    assert await _count_runs() == 0  # worker has not run yet


# --------------------------------------------------------------------------- #
# Spans appear in SQLite within ~100ms
# --------------------------------------------------------------------------- #
async def test_span_persisted_after_flush() -> None:
    """An emitted span is written to SQLite once the worker flushes."""
    await tracer._emit_span(_span(run_id="abc12345-eee"))
    await asyncio.sleep(0.2)
    async with get_session() as session:
        run = (await session.execute(select(Run))).scalar_one()
    assert run.id == "abc12345-eee"
    assert run.agent_name == "test-agent"


async def test_tool_calls_persisted_with_run() -> None:
    """Tool calls on a span are written alongside the run."""
    call = ToolCall(
        tool_name="search",
        params={"q": "x"},
        result={"hits": 1},
        duration_ms=12.0,
        error=None,
        timestamp=0.0,
    )
    await tracer._emit_span(_span(tool_calls=[call]))
    await asyncio.sleep(0.2)
    async with get_session() as session:
        rec = (await session.execute(select(ToolCallRecord))).scalar_one()
    assert rec.tool_name == "search"
    assert rec.run_id == "run-0001abcd"


# --------------------------------------------------------------------------- #
# A DB-write failure is caught; the worker keeps running
# --------------------------------------------------------------------------- #
async def test_write_failure_swallowed_and_worker_survives(monkeypatch) -> None:
    """A storage error is logged and swallowed; later spans still persist."""
    original = tracer._write_batch

    async def boom(batch) -> None:
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(tracer, "_write_batch", boom)
    await tracer._emit_span(_span(run_id="fails-001"))
    await asyncio.sleep(0.2)  # worker tries, raises, logs, continues

    assert tracer._worker_task is not None
    assert not tracer._worker_task.done()  # loop did not exit on error

    monkeypatch.setattr(tracer, "_write_batch", original)
    await tracer._emit_span(_span(run_id="ok-002"))
    await asyncio.sleep(0.2)
    async with get_session() as session:
        run = (await session.execute(select(Run))).scalar_one()
    assert run.id == "ok-002"  # the failed batch is dropped, not retried forever


# --------------------------------------------------------------------------- #
# Console output is printed before the DB write
# --------------------------------------------------------------------------- #
async def test_console_success_line(capsys) -> None:
    """A successful span prints the ✓ line with the 8-char run prefix."""
    await tracer._emit_span(_span(run_id="deadbeef-1111", duration_ms=234.0))
    out = capsys.readouterr().out  # captured before any flush
    assert "[failprobe] run=deadbeef agent=test-agent status=✓ duration=234ms" in out


async def test_console_failure_line(capsys) -> None:
    """A failed span prints the ✗ line including the failure type."""
    span = _span(
        run_id="cafebabe-2222",
        duration_ms=1203.0,
        success=False,
        failure_type="INFINITE_LOOP",
    )
    await tracer._emit_span(span)
    out = capsys.readouterr().out
    assert (
        "[failprobe] run=cafebabe agent=test-agent "
        "status=✗ failure=INFINITE_LOOP duration=1203ms" in out
    )


async def test_console_degrades_when_stream_cannot_encode(monkeypatch) -> None:
    """A cp1252-style stream that rejects ✓/✗ degrades to ASCII, never raising."""
    written: list[str] = []

    def raising_print(*args, **kwargs) -> None:
        raise UnicodeEncodeError("charmap", "✓", 0, 1, "undefined")

    monkeypatch.setattr("builtins.print", raising_print)
    monkeypatch.setattr(tracer.sys.stdout, "write", lambda s: written.append(s))

    await tracer._emit_span(_span(run_id="deadbeef-9999"))
    out = "".join(written)
    assert "[failprobe] run=deadbeef agent=test-agent status=" in out
    assert "✓" not in out  # the unencodable glyph was replaced
    # The span was still enqueued and persists despite the print failure.
    await asyncio.sleep(0.2)
    assert await _count_runs() == 1


async def test_console_suppressed_when_disabled(capsys, monkeypatch) -> None:
    """No console line is printed when ``emit_console`` is False."""
    from failprobe.config import ProbeConfig, configure

    monkeypatch.setattr("failprobe.tracer.get_config", lambda: ProbeConfig(emit_console=False))
    configure(ProbeConfig(emit_console=False))
    await tracer._emit_span(_span())
    assert capsys.readouterr().out == ""


# --------------------------------------------------------------------------- #
# 50+ spans queued at once are flushed in a single transaction
# --------------------------------------------------------------------------- #
async def test_batch_of_50_flushed_in_single_transaction(monkeypatch) -> None:
    """Fifty spans enqueued before the worker runs flush as one batch."""
    sizes: list[int] = []
    original = tracer._write_batch

    async def spy(batch) -> None:
        sizes.append(len(batch))
        await original(batch)

    monkeypatch.setattr(tracer, "_write_batch", spy)

    # No suspension point in _emit_span, so all 50 enqueue before the worker runs.
    for i in range(50):
        await tracer._emit_span(_span(run_id=f"run-{i:04d}"))
    await asyncio.sleep(0.25)

    assert sizes == [50]  # exactly one transaction, carrying all 50 spans
    assert await _count_runs() == 50
