# Task 04 — Failure Taxonomy (`agentprobe/classifier/taxonomy.py`)

**Phase:** Month 1, Week 1
**Module:** `agentprobe/classifier/taxonomy.py`

---

## Goal

Define the canonical `FailureType` enum and its human-readable descriptions. This is the single source of truth for all 15 failure categories used across the classifier, storage, API, and dashboard.

---

## Implementation

### `agentprobe/classifier/taxonomy.py`

```python
from enum import Enum

class FailureType(Enum):
    # Tool-use failures
    WRONG_TOOL        = "wrong_tool"
    BAD_PARAMS        = "bad_params"
    MISSING_TOOL      = "missing_tool"
    TOOL_TIMEOUT      = "tool_timeout"
    TOOL_API_ERROR    = "tool_api_error"

    # Reasoning failures
    HALLUCINATED_CALL = "hallucinated_call"
    CONTEXT_OVERFLOW  = "context_overflow"
    INFINITE_LOOP     = "infinite_loop"
    WRONG_FORMAT      = "wrong_format"

    # Output failures
    TASK_FAILED       = "task_failed"
    PARTIAL_SUCCESS   = "partial_success"
    REFUSED           = "refused"

    # System failures
    EXCEPTION         = "exception"
    TIMEOUT           = "timeout"
    UNKNOWN           = "unknown"


FAILURE_DESCRIPTIONS: dict[FailureType, str] = {
    FailureType.WRONG_TOOL:        "Agent called a semantically irrelevant tool for the task.",
    FailureType.BAD_PARAMS:        "Tool rejected the call due to invalid or missing parameters.",
    FailureType.MISSING_TOOL:      "Agent attempted to call a tool that was not registered in the allowed toolset.",
    FailureType.TOOL_TIMEOUT:      "A tool call exceeded its timeout limit.",
    FailureType.TOOL_API_ERROR:    "A tool returned an HTTP or API-level error (4xx/5xx).",
    FailureType.HALLUCINATED_CALL: "Agent called a tool that does not exist in any available toolset.",
    FailureType.CONTEXT_OVERFLOW:  "Token count exceeded the context window threshold mid-run.",
    FailureType.INFINITE_LOOP:     "The same (tool, params) fingerprint was called repeatedly above the loop threshold.",
    FailureType.WRONG_FORMAT:      "Agent output did not match the expected schema or format.",
    FailureType.TASK_FAILED:       "Run completed but the output is factually wrong or does not satisfy the task.",
    FailureType.PARTIAL_SUCCESS:   "Some subtasks completed successfully but not all required ones.",
    FailureType.REFUSED:           "The LLM declined to complete the task.",
    FailureType.EXCEPTION:         "An unhandled Python exception was raised during the run.",
    FailureType.TIMEOUT:           "The full agent run exceeded its wall-clock timeout.",
    FailureType.UNKNOWN:           "Classifier could not determine the failure reason.",
}
```

---

## Full Failure Reference Table

| FailureType | Trigger condition | Example |
|---|---|---|
| `WRONG_TOOL` | Agent called a semantically irrelevant tool | Weather query → calls `send_email` |
| `BAD_PARAMS` | Tool rejected due to invalid parameters | `search(query=None)` |
| `MISSING_TOOL` | Tool name not in allowed toolset | Calls `get_stock_price` but it wasn't registered |
| `TOOL_TIMEOUT` | Tool call exceeded timeout | `fetch_url` times out after 30s |
| `TOOL_API_ERROR` | Tool returned HTTP error | 429 rate limit, 500 server error |
| `HALLUCINATED_CALL` | Tool called that doesn't exist in any toolset | Calls `browse_web` when no browser tool is available |
| `CONTEXT_OVERFLOW` | Token count > threshold mid-run | 128k context exceeded |
| `INFINITE_LOOP` | Same (tool, params) repeated ≥ N times | Calls `search("weather Delhi")` 5 times |
| `WRONG_FORMAT` | Output doesn't match expected schema | JSON expected, markdown returned |
| `TASK_FAILED` | Run completed, output is wrong | Answer is factually incorrect |
| `PARTIAL_SUCCESS` | Some subtasks done, not all | Booked flight but not hotel |
| `REFUSED` | LLM declined to complete | "I cannot help with that" |
| `EXCEPTION` | Python exception raised | `KeyError`, `AttributeError` |
| `TIMEOUT` | Full run wall-clock timeout | 30s limit exceeded |
| `UNKNOWN` | None of the above matched | Classifier couldn't determine reason |

---

## Acceptance Criteria

- [ ] `len(FailureType)` == 15
- [ ] Every `FailureType` member has an entry in `FAILURE_DESCRIPTIONS`
- [ ] `FailureType("wrong_tool")` resolves to `FailureType.WRONG_TOOL`
- [ ] `FAILURE_DESCRIPTIONS[FailureType.UNKNOWN]` returns a non-empty string
- [ ] No `FailureType` is missing from the descriptions dict (enforced by a unit test)
