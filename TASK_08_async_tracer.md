# Task 08 — Async Span Emitter (`agentprobe/tracer.py`)

**Phase:** Month 1, Week 3
**Module:** `agentprobe/tracer.py`

---

## Goal

Implement the async span emission pipeline. Spans are collected in an in-memory queue and flushed to storage in batches, never blocking the agent. This is the fire-and-forget backend that `@probe` calls via `asyncio.create_task`.

---

## Interface

```python
async def _emit_span(span: AgentSpan) -> None:
    """
    Phase 1 (Month 1): write to SQLite via storage layer.
    Phase 2 (Month 2): if api_url set, also POST to /collector endpoint.
    Always: print to console if emit_console=True.
    """
```

---

## Batching Behaviour

```python
_queue: asyncio.Queue[AgentSpan] = asyncio.Queue()

async def _flush_worker() -> None:
    """
    Background coroutine. Drains the queue:
    - every 100ms, OR
    - whenever the queue reaches 50 items
    Whichever comes first.
    Writes the batch to storage in a single DB transaction.
    """
```

### Rules

- `_emit_span` puts the span on `_queue` and returns immediately.
- `_flush_worker` must be started once at process startup (by `@probe` on first use, or by `init_db()`).
- All DB writes happen inside the flush worker, not in `_emit_span`.
- The flush worker must be wrapped in `try/except Exception` — a storage error must never propagate.

---

## Console output (when `emit_console=True`)

Print a single line per span immediately (not batched), before the DB write:

```
[agentprobe] run=<run_id_prefix> agent=<name> status=✓ duration=234ms
[agentprobe] run=<run_id_prefix> agent=<name> status=✗ failure=INFINITE_LOOP duration=1203ms
```

Use the first 8 characters of the UUID for the run prefix.

---

## Phase 2 addition (Month 2 only — do not build in Month 1)

```python
async def _post_to_api(span: AgentSpan, api_url: str) -> None:
    """POST span JSON to {api_url}/collector. Fire-and-forget."""
    async with httpx.AsyncClient() as client:
        await client.post(f"{api_url}/collector", json=span_to_dict(span), timeout=5.0)
```

---

## Acceptance Criteria

- [ ] `_emit_span(span)` returns immediately (does not await storage)
- [ ] Spans written to `_queue` appear in SQLite within 100ms under normal load
- [ ] A DB write failure is caught and logged to stderr — the queue continues processing
- [ ] Console output is printed before the DB write (not blocked by it)
- [ ] 50+ spans queued at once are flushed in a single transaction
- [ ] `_flush_worker` keeps running after an error (does not exit the loop)
