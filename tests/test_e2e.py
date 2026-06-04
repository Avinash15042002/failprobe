"""End-to-end pipeline test (TASK 16 item 4).

Exercises the real ``@probe`` → tracer → storage path: five decorated agent
calls are made, their spans are emitted fire-and-forget, the background flush
worker drains them to SQLite, and we then assert that five runs landed in the
DB with the failure types the rule-based classifier should have assigned.

The decorator persists spans *directly* to the database via the tracer — the
HTTP ``_post_to_api`` path is deferred to Phase 2 (Rule 5) — so this is the
faithful full-stack test for the current architecture. It is marked ``e2e`` and
excluded from standard CI (run with ``pytest tests/test_e2e.py -m e2e``).

It runs self-contained against a fresh temp SQLite file (no external services
required), so ``docker compose up`` is not needed for it to pass.
"""

import asyncio
from typing import Optional

import pytest
from sqlalchemy import select

from agentprobe import probe
from agentprobe import tracer
from agentprobe.classifier.taxonomy import FailureType
from agentprobe.models import ToolCall
from agentprobe.storage import db
from agentprobe.storage.db import get_session, init_db
from agentprobe.storage.models import Run

pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
async def _fresh_pipeline(tmp_path, monkeypatch) -> None:
    """Fresh temp DB + reset DB/tracer singletons, then create tables.

    Mirrors the isolation pattern in ``test_tracer.py`` so the module-level
    queue and flush worker bind to this test's event loop.
    """
    db_file = tmp_path / "e2e.db"
    monkeypatch.setenv("AGENTPROBE_DB_URL", f"sqlite+aiosqlite:///{db_file.as_posix()}")
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_session_factory", None)
    monkeypatch.setattr(tracer, "_queue", asyncio.Queue())
    monkeypatch.setattr(tracer, "_worker_task", None)
    monkeypatch.setattr(tracer, "_worker_loop", None)
    await init_db()


# --------------------------------------------------------------------------- #
# Five decorated agents, one per outcome the classifier should detect.
# --------------------------------------------------------------------------- #
@probe(name="ok-agent")
async def ok_agent(query: str) -> str:
    """A clean success — no failure should be classified."""
    return f"Handled: {query}"


@probe(name="boom-agent")
async def boom_agent(query: str) -> str:
    """Raises — the decorator records the traceback → EXCEPTION."""
    raise RuntimeError("upstream failure")


@probe(name="loop-agent")
async def loop_agent(query: str, _probe_collector: Optional[list] = None) -> str:
    """Records four identical (tool, params) calls → INFINITE_LOOP."""
    for _ in range(4):
        if _probe_collector is not None:
            _probe_collector.append(
                ToolCall(
                    tool_name="search",
                    params={"q": query},
                    result=None,
                    duration_ms=1.0,
                    error=None,
                    timestamp=0.0,
                )
            )
    return "gave up after looping"


@probe(name="overflow-agent")
async def overflow_agent(query: str) -> dict:
    """Returns a usage payload over the token threshold → CONTEXT_OVERFLOW."""
    return {"answer": "truncated", "usage": {"total_tokens": 150_000}}


@probe(name="refuse-agent")
async def refuse_agent(query: str) -> str:
    """Returns a refusal phrase → REFUSED."""
    return "I cannot help with that request."


async def test_five_decorated_calls_persist_with_failure_types() -> None:
    """Run 5 decorated agents → 5 runs in the DB with the expected outcomes."""
    await ok_agent("weather in Delhi")
    with pytest.raises(RuntimeError):
        await boom_agent("crash please")  # re-raised transparently, span still emitted
    await loop_agent("population of Atlantis")
    await overflow_agent("summarize a huge document")
    await refuse_agent("do something disallowed")

    # Let the fire-and-forget create_task emissions run and the worker flush.
    await asyncio.sleep(0.4)

    async with get_session() as session:
        runs = (await session.execute(select(Run))).scalars().all()

    # 1. Exactly five runs persisted.
    assert len(runs) == 5

    by_agent = {run.agent_name: run for run in runs}
    assert set(by_agent) == {
        "ok-agent",
        "boom-agent",
        "loop-agent",
        "overflow-agent",
        "refuse-agent",
    }

    # 2. Failure types match what the rule-based classifier should assign.
    assert by_agent["ok-agent"].success is True
    assert by_agent["ok-agent"].failure_type is None

    assert by_agent["boom-agent"].success is False
    assert by_agent["boom-agent"].failure_type == FailureType.EXCEPTION.value

    assert by_agent["loop-agent"].failure_type == FailureType.INFINITE_LOOP.value
    assert by_agent["overflow-agent"].failure_type == FailureType.CONTEXT_OVERFLOW.value
    assert by_agent["refuse-agent"].failure_type == FailureType.REFUSED.value
