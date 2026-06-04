"""Async, batched span emission pipeline for AgentProbe (Task 08).

Spans captured by the ``@probe`` decorator are handed to :func:`_emit_span`,
which puts them on an in-memory queue and returns immediately — never blocking
the agent. A single background coroutine, :func:`_flush_worker`, drains the
queue to the storage layer in batches: every 100 ms, or as soon as 50 spans
have accumulated, whichever comes first. The whole batch is written in one DB
transaction.

Two hard constraints (spec §5.1, Rule 2):

* **Never block.** ``_emit_span`` only enqueues and prints the immediate
  console line; all DB I/O happens inside the worker.
* **Never crash, never exit.** Both ``_emit_span`` and the worker body are
  wrapped in ``try/except Exception``; a storage failure is logged to stderr
  and the worker loop continues with the next batch — it never exits.

Phase 2 (Month 2) will add an optional ``_post_to_api`` path when
``ProbeConfig.api_url`` is set. That is intentionally not built here (Rule 5).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Optional

from agentprobe.config import get_config
from agentprobe.models import AgentSpan, ToolCall
from agentprobe.storage.db import get_session
from agentprobe.storage.models import Run, ToolCallRecord

logger = logging.getLogger("agentprobe")

# Flush triggers (spec §"Batching Behaviour").
FLUSH_INTERVAL_S: float = 0.1  # 100 ms
BATCH_SIZE: int = 50

# Module-level in-memory queue and the single background worker draining it.
# ``_worker_loop`` records the event loop the current queue/worker are bound to
# so the pipeline survives being driven from a fresh loop (e.g. one
# ``asyncio.run`` per test) without an "attached to a different loop" error.
_queue: "asyncio.Queue[AgentSpan]" = asyncio.Queue()
_worker_task: Optional["asyncio.Task[None]"] = None
_worker_loop: Optional[asyncio.AbstractEventLoop] = None


def _to_json(value: Any) -> str:
    """Serialize an arbitrary payload to a JSON string, never raising.

    Non-JSON-serializable members fall back to ``str``; a total failure falls
    back to ``json.dumps(str(value))`` so the flush can always proceed.
    """
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return json.dumps(str(value))


def _span_to_run(span: AgentSpan) -> Run:
    """Map an in-memory :class:`AgentSpan` to a :class:`Run` ORM row.

    Nested ``input``/``output``/``metadata`` payloads are JSON-serialized to
    flat text columns (per the storage schema). ``created_at`` is reconstructed
    from the span's Unix ``timestamp`` to preserve the true capture time.
    """
    return Run(
        id=span.run_id,
        agent_name=span.agent_name,
        input_text=_to_json(span.input),
        output_text=_to_json(span.output) if span.output is not None else None,
        duration_ms=span.duration_ms,
        tokens_used=span.tokens_used,
        model=span.model,
        success=span.success,
        failure_type=span.failure_type,
        failure_msg=span.failure_msg,
        exception=span.exception,
        tags=_to_json(span.metadata),
        created_at=datetime.fromtimestamp(span.timestamp, tz=timezone.utc),
    )


def _toolcall_to_record(run_id: str, call: ToolCall) -> ToolCallRecord:
    """Map an in-memory :class:`ToolCall` to a :class:`ToolCallRecord` row."""
    return ToolCallRecord(
        run_id=run_id,
        tool_name=call.tool_name,
        params=_to_json(call.params),
        result=_to_json(call.result) if call.result is not None else None,
        duration_ms=call.duration_ms,
        error=call.error,
        timestamp=datetime.fromtimestamp(call.timestamp, tz=timezone.utc),
    )


def _print_console(span: AgentSpan) -> None:
    """Print the immediate one-line console summary for ``span``.

    No-op when ``ProbeConfig.emit_console`` is ``False``. The run prefix is the
    first 8 characters of the UUID; duration is rounded to whole milliseconds.
    On a stream that cannot encode ``✓``/``✗`` (e.g. a redirected cp1252 pipe on
    Windows) the line degrades to ASCII rather than being dropped.
    """
    if not get_config().emit_console:
        return
    prefix = span.run_id[:8]
    duration = int(round(span.duration_ms))
    if span.success:
        line = (
            f"[agentprobe] run={prefix} agent={span.agent_name} "
            f"status=✓ duration={duration}ms"
        )
    else:
        failure = span.failure_type or "UNKNOWN"
        line = (
            f"[agentprobe] run={prefix} agent={span.agent_name} "
            f"status=✗ failure={failure} duration={duration}ms"
        )
    try:
        print(line)
    except UnicodeEncodeError:
        sys.stdout.write(line.encode("ascii", "replace").decode("ascii") + "\n")


def _ensure_worker() -> None:
    """Start (or rebind) the background flush worker for the running loop.

    Called by every :func:`_emit_span`. Starts the worker on first use. If the
    current running loop differs from the one the queue/worker were bound to
    (a fresh ``asyncio.run``), the queue is recreated and a new worker is
    started on this loop. Uses ``asyncio.ensure_future`` — never
    ``asyncio.run`` (Task 08, item 2).
    """
    global _queue, _worker_task, _worker_loop
    loop = asyncio.get_running_loop()
    if _worker_loop is not loop:
        _queue = asyncio.Queue()
        _worker_loop = loop
        _worker_task = asyncio.ensure_future(_flush_worker())
    elif _worker_task is None or _worker_task.done():
        _worker_task = asyncio.ensure_future(_flush_worker())


async def _emit_span(span: AgentSpan) -> None:
    """Enqueue ``span`` for batched persistence and return immediately.

    Started fire-and-forget by ``@probe`` via ``asyncio.create_task``. Ensures
    the flush worker is running, enqueues the span, and prints the immediate
    console line — all before any DB write (which happens later in the worker).
    The body is fully wrapped so an internal error can never propagate to the
    agent (Rule 2).

    Args:
        span: The captured, already-classified span to persist.
    """
    try:
        _ensure_worker()
        # Enqueue before printing so a console-encoding error cannot drop the
        # span; both still happen before the worker's DB write.
        _queue.put_nowait(span)
        _print_console(span)
    except Exception:  # noqa: BLE001 — AgentProbe must never crash the agent.
        logger.error("AgentProbe error while emitting span", exc_info=True)


async def _drain_batch() -> list[AgentSpan]:
    """Collect the next batch of spans to flush.

    Blocks up to :data:`FLUSH_INTERVAL_S` for the first span (returning an empty
    list on timeout), then greedily pulls any already-queued spans up to
    :data:`BATCH_SIZE`. This realizes "flush every 100 ms OR when the queue
    reaches 50 items, whichever comes first".
    """
    try:
        first = await asyncio.wait_for(_queue.get(), timeout=FLUSH_INTERVAL_S)
    except asyncio.TimeoutError:
        return []
    batch = [first]
    while len(batch) < BATCH_SIZE:
        try:
            batch.append(_queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    return batch


async def _write_batch(batch: list[AgentSpan]) -> None:
    """Persist a batch of spans (with their tool calls) in one transaction."""
    async with get_session() as session:
        for span in batch:
            session.add(_span_to_run(span))
            for call in span.tool_calls:
                session.add(_toolcall_to_record(span.run_id, call))
        await session.commit()


async def _flush_worker() -> None:
    """Drain the span queue to storage in batches, forever.

    Each iteration collects a batch (:func:`_drain_batch`) and writes it in a
    single transaction. The whole body is wrapped in ``try/except Exception``:
    a storage error is logged to stderr and the loop continues with the next
    batch — the worker never exits on error (Task 08, acceptance criteria).
    """
    while True:
        try:
            batch = await _drain_batch()
            if batch:
                await _write_batch(batch)
        except Exception:  # noqa: BLE001 — worker must survive any failure.
            logger.error("AgentProbe flush worker error", exc_info=True)
