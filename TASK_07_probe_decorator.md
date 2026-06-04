# Task 07 — `@probe` Decorator (`agentprobe/decorator.py`)

**Phase:** Month 1, Week 1
**Module:** `agentprobe/decorator.py`

---

## Goal

Implement the `@probe` decorator — the primary user-facing API. It must wrap async agent functions transparently, capture a full `AgentSpan`, classify failures, and emit spans asynchronously without ever blocking or crashing the user's agent.

---

## Signature

```python
def probe(
    name: str,
    expected_output: Any = None,
    timeout: Optional[float] = None,
    model: Optional[str] = None,
    tags: Optional[dict] = None,
) -> Callable:
```

---

## Behaviour Contract

### What the decorator must record

| Field | Source |
|---|---|
| `run_id` | `uuid.uuid4()` generated at call time |
| `agent_name` | `name` argument to `@probe` |
| `input` | positional/keyword args of the wrapped function |
| `output` | return value of the wrapped function |
| `duration_ms` | wall-clock time from call start to end |
| `tokens_used` | extracted from return value if it's a dict with `"usage"` key, else `None` |
| `model` | `model` kwarg, or auto-detected if return value exposes it |
| `success` | `True` if no exception; `False` otherwise |
| `exception` | `traceback.format_exc()` on exception, else `None` |
| `tool_calls` | contents of injected `_probe_collector` list (see below) |

### Execution order

```
1. Generate run_id
2. Record start time
3. Inject _probe_collector (empty list) into kwargs if agent accepts it
4. Call wrapped function inside try/except
5. Record end time → duration_ms
6. Build AgentSpan
7. Call FailureClassifier.classify(span)  ← synchronous, no await
8. asyncio.create_task(_emit_span(span))  ← fire-and-forget, never await
9. Return original output (or re-raise original exception)
```

### Tool call injection pattern

```python
# If the wrapped function has a _probe_collector parameter:
collector: list[ToolCall] = []
kwargs["_probe_collector"] = collector
# After call: span.tool_calls = collector
```

This is the **opt-in** pattern. If the function does not accept `_probe_collector`, skip injection silently.

### Error isolation

```python
try:
    result = classify_and_emit(span)
except Exception as e:
    # AgentProbe failed internally — log to stderr, do NOT raise
    import sys
    print(f"[agentprobe] internal error: {e}", file=sys.stderr)
```

**AgentProbe must never crash the user's agent.** If classification or emission fails, log to stderr and continue.

---

## Usage Examples

```python
from agentprobe import probe

# Basic usage
@probe(name="my-agent")
async def run_agent(query: str) -> str:
    return await your_existing_agent.arun(query)

# With tool call tracking (opt-in)
@probe(name="weather-agent")
async def weather_agent(query: str, _probe_collector: list = None) -> str:
    tool_call = ToolCall(tool_name="get_weather", params={"city": "Delhi"}, ...)
    if _probe_collector is not None:
        _probe_collector.append(tool_call)
    return result
```

---

## Public API export

Add to `agentprobe/__init__.py`:

```python
from agentprobe.decorator import probe
```

---

## Acceptance Criteria

- [ ] `@probe(name="x")` wraps an async function without changing its signature or return value
- [ ] The decorated function still raises the original exception to the caller on failure
- [ ] An internal AgentProbe crash does NOT propagate to the caller
- [ ] `asyncio.create_task` is used for span emission — never `await`
- [ ] `_probe_collector` is injected only when the wrapped function's signature includes that parameter
- [ ] `duration_ms` is always recorded, even when the function raises
- [ ] Span is passed to `FailureClassifier.classify()` before emission
