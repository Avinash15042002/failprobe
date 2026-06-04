# Task 16 — Test Suite (`tests/`)

**Phase:** Month 1 Week 1 (classifier tests) → Month 2 (eval tests) → Month 3 (regression tests)
**Module:** `tests/`

---

## Goal

Write the full test suite covering the classifier, meta-evaluator, regression engine, and API. Tests are the proof that the system works — they also serve as living documentation of expected behaviour.

---

## Directory Structure

```
tests/
├── conftest.py
├── fixtures/
│   ├── span_success.json
│   ├── span_wrong_tool.json
│   ├── span_infinite_loop.json
│   ├── span_exception.json
│   └── span_context_overflow.json
├── test_classifier.py
├── test_meta_eval.py
├── test_regression.py
└── test_api.py
```

---

## `conftest.py`

```python
import pytest
from agentprobe.models import AgentSpan, ToolCall
from agentprobe.classifier.taxonomy import FailureType

def make_span(**kwargs) -> AgentSpan:
    """Factory for creating test AgentSpan objects with sane defaults."""
    defaults = {
        "run_id": "test-run-id",
        "agent_name": "test-agent",
        "input": "test input",
        "output": "test output",
        "duration_ms": 100.0,
        "tool_calls": [],
        "success": True,
    }
    return AgentSpan(**{**defaults, **kwargs})

def make_tool_call(tool_name: str, params: dict, error: str = None) -> ToolCall:
    return ToolCall(tool_name=tool_name, params=params, result=None, duration_ms=50.0, error=error, timestamp=0.0)
```

---

## `test_classifier.py` — Required Tests

Minimum **2 tests per FailureType = 30 tests total**. Every `FailureType` must be tested.

```python
# Examples — expand for all 15 types

def test_classifies_exception():
    span = make_span(exception="RuntimeError: API failed", success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.EXCEPTION

def test_classifies_timeout():
    span = make_span(exception="asyncio.TimeoutError: ...", success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.TIMEOUT

def test_classifies_infinite_loop():
    calls = [make_tool_call("search", {"q": "weather"}) for _ in range(4)]
    span = make_span(tool_calls=calls, success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.INFINITE_LOOP

def test_classifies_tool_timeout():
    calls = [make_tool_call("fetch_url", {}, error="Connection timed out")]
    span = make_span(tool_calls=calls, success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.TOOL_TIMEOUT

def test_classifies_bad_params():
    calls = [make_tool_call("search", {}, error="validation error: query is required")]
    span = make_span(tool_calls=calls, success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.BAD_PARAMS

def test_classifies_context_overflow():
    span = make_span(tokens_used=150_000, success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.CONTEXT_OVERFLOW

def test_classifies_refused():
    span = make_span(output="I cannot help with that request.", success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.REFUSED

def test_success_returns_none():
    span = make_span(success=True, output="The weather is 38C")
    ftype, msg = classifier.classify(span)
    assert ftype is None
    assert msg == "success"

def test_priority_exception_over_loop():
    """Exception should be caught before loop detection."""
    calls = [make_tool_call("search", {"q": "x"}) for _ in range(5)]
    span = make_span(exception="RuntimeError", tool_calls=calls, success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.EXCEPTION  # not INFINITE_LOOP

# Continue for: MISSING_TOOL, TOOL_API_ERROR, HALLUCINATED_CALL, WRONG_FORMAT,
#               TASK_FAILED, PARTIAL_SUCCESS, UNKNOWN
```

---

## `test_meta_eval.py` — Required Tests

```python
def test_meta_eval_perfect_judge():
    """Judge always agrees with human → accuracy = 1.0"""
    ...

def test_meta_eval_random_judge():
    """Judge at chance → accuracy ≈ 0.5, CI should contain 0.5"""
    ...

def test_bootstrap_ci_width_increases_with_less_data():
    """More data → narrower CI"""
    ci_small = bootstrap_ci([True, False] * 10)
    ci_large = bootstrap_ci([True, False] * 100)
    assert (ci_small[1] - ci_small[0]) > (ci_large[1] - ci_large[0])

def test_meta_eval_warns_small_dataset():
    """n < 30 should include a warning in the report"""
    ...
```

---

## `test_regression.py` — Required Tests

```python
def test_no_regression_when_same():
    before = [True] * 90 + [False] * 10
    after = [True] * 90 + [False] * 10
    p, sig = mcnemar_test(before, after)
    assert not sig

def test_regression_detected_on_5pct_drop():
    before = [True] * 95 + [False] * 5
    after = [True] * 89 + [False] * 11
    assert is_regression(0.95, 0.89, bootstrap_ci([b == a for b, a in zip(before, after)]))

def test_no_alert_when_not_significant():
    """Delta is 6% but p=0.4 → should NOT flag as regression"""
    ...
```

---

## `test_api.py` — Integration Tests

```python
@pytest.fixture
async def client():
    """httpx.AsyncClient against a real FastAPI app with in-memory SQLite."""
    async with AsyncClient(app=app, base_url="http://test") as c:
        yield c

async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

async def test_get_runs_empty(client):
    r = await client.get("/runs")
    assert r.status_code == 200
    assert r.json()["total"] == 0

async def test_get_run_not_found(client):
    r = await client.get("/runs/nonexistent-id")
    assert r.status_code == 404
    assert "error" in r.json()
```

---

## Test Fixtures (`tests/fixtures/`)

Provide at least 5 JSON files representing real `AgentSpan` objects:

- `span_success.json` — successful run, no failures
- `span_wrong_tool.json` — tool call with semantically wrong tool
- `span_infinite_loop.json` — 4 identical (tool, params) calls
- `span_exception.json` — run that raised a RuntimeError
- `span_context_overflow.json` — `tokens_used: 150000`

---

## Acceptance Criteria

- [ ] `pytest tests/ -v` exits 0
- [ ] Minimum 30 classifier tests (2 per FailureType)
- [ ] Every `FailureType` is covered by at least one test
- [ ] `test_api.py` runs against real FastAPI app (not mocked)
- [ ] All test fixtures are valid JSON that deserialise into `AgentSpan`
