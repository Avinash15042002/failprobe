# Task 05 — Failure Classifier (`agentprobe/classifier/`)

**Phase:** Month 1, Week 1
**Module:** `agentprobe/classifier/classifier.py` + `rules/`

---

## Goal

Implement the rule-based `FailureClassifier` and all four rule sub-modules. This must classify ≥90% of failures with zero LLM calls, completing in <10ms at the 99th percentile.

---

## Files to Create

```
agentprobe/classifier/
├── __init__.py
├── classifier.py          ← main FailureClassifier class
├── taxonomy.py            ← (already done in Task 04)
└── rules/
    ├── __init__.py
    ├── tool_errors.py     ← TOOL_TIMEOUT / BAD_PARAMS / MISSING_TOOL / TOOL_API_ERROR
    ├── loop_detector.py   ← INFINITE_LOOP
    ├── hallucination.py   ← HALLUCINATED_CALL
    └── context.py         ← CONTEXT_OVERFLOW
```

---

## `classifier.py` — FailureClassifier

### Interface

```python
class FailureClassifier:
    def classify(self, span: AgentSpan) -> tuple[FailureType | None, str]:
        """
        Returns (FailureType, explanation) or (None, "success") if no failure.
        Synchronous. Must complete in <10ms for p99. No network or LLM calls.
        """
```

### Classification priority order (check in this exact order, stop at first match)

1. `span.exception` is set AND contains "TimeoutError" → `TIMEOUT`
2. `span.exception` is set (any other exception) → `EXCEPTION`
3. Loop detection on `span.tool_calls` → `INFINITE_LOOP`
4. Any `ToolCall.error` is set → delegate to `_classify_tool_error(tc)` → one of the tool error types
5. `span.tokens_used > config.token_overflow_threshold` → `CONTEXT_OVERFLOW`
6. Output text matches refusal pattern → `REFUSED`
7. `span.success is False` and `span.failure_msg` contains "partial" (case-insensitive) → `PARTIAL_SUCCESS`
8. `span.success is False` → `TASK_FAILED`
9. Fall through → `(None, "success")`

---

## `rules/tool_errors.py`

Parse `ToolCall.error` string and map to failure type:

| Error pattern (case-insensitive) | FailureType |
|---|---|
| "timeout", "timed out" | `TOOL_TIMEOUT` |
| "not found", "no tool", "undefined", "does not exist" | `MISSING_TOOL` |
| "invalid", "missing", "required", "type error", "validation" | `BAD_PARAMS` |
| HTTP status codes (4xx/5xx in string, e.g. "404", "500") | `TOOL_API_ERROR` |
| Anything else | `TOOL_API_ERROR` |

```python
def classify_tool_error(error: str) -> FailureType:
    ...
```

---

## `rules/loop_detector.py`

```python
def detect_loop(tool_calls: list[ToolCall], threshold: int) -> tuple[bool, str]:
    """
    Returns (is_loop, explanation).
    Algorithm:
      fingerprint = (tool_name, frozenset(params.items()))
      If any fingerprint appears >= threshold times → True
      Also: if last `threshold` calls have identical tool_name (regardless of params) → True
      If params contain unhashable values, fall back to str(params) for fingerprint.
    """
```

---

## `rules/hallucination.py`

```python
def detect_hallucinated_calls(
    tool_calls: list[ToolCall],
    allowed_tools: list[str],
) -> tuple[bool, str]:
    """
    If allowed_tools is empty/None, skip and return (False, "").
    Otherwise: any tool_call.tool_name not in allowed_tools → hallucinated.
    """
```

---

## `rules/context.py`

```python
def detect_context_overflow(tokens_used: int | None, threshold: int) -> bool:
    if tokens_used is None:
        return False
    return tokens_used > threshold
```

---

## Refusal patterns

In `classifier.py`, define:

```python
REFUSAL_PATTERNS = [
    "i cannot help",
    "i can't help",
    "i am unable to",
    "i'm unable to",
    "i must decline",
    "i cannot assist",
    "i won't be able to",
]

def _is_refusal(output: Any) -> bool:
    if not isinstance(output, str):
        return False
    text = output.lower()
    return any(p in text for p in REFUSAL_PATTERNS)
```

---

## Acceptance Criteria

- [ ] `FailureClassifier().classify(span)` is synchronous and makes no I/O calls
- [ ] Priority order is enforced: an exception span with a loop is classified as `EXCEPTION`, not `INFINITE_LOOP`
- [ ] `loop_detector` handles unhashable params gracefully (no crash)
- [ ] `hallucination` detector returns `(False, "")` when `allowed_tools` is empty
- [ ] A successful span returns `(None, "success")`
- [ ] All tests in `tests/test_classifier.py` pass (see Task 14 for test spec — minimum 2 tests per FailureType = 30 tests)
