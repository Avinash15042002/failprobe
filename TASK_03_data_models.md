# Task 03 — Core Data Models (`AgentSpan`, `ToolCall`, `GoldenCase`)

**Phase:** Month 1, Week 1
**Module:** `agentprobe/models.py` (in-memory models, NOT ORM)

---

## Goal

Define the canonical in-memory Python dataclasses that flow between the decorator, classifier, evaluator, and storage. These are **not** SQLAlchemy ORM models — those live in `agentprobe/storage/models.py` (Task 06).

---

## Implementation

### `agentprobe/models.py`

```python
from dataclasses import dataclass, field
from typing import Any, Optional, Literal
from datetime import datetime

from agentprobe.classifier.taxonomy import FailureType


@dataclass
class ToolCall:
    tool_name:   str
    params:      dict
    result:      Any
    duration_ms: float
    error:       Optional[str]
    timestamp:   float  # Unix timestamp


@dataclass
class AgentSpan:
    run_id:       str               # UUID4
    agent_name:   str
    input:        Any
    output:       Any
    duration_ms:  float
    tool_calls:   list[ToolCall] = field(default_factory=list)
    tokens_used:  Optional[int] = None
    model:        Optional[str] = None
    success:      bool = True
    failure_type: Optional[FailureType] = None
    failure_msg:  Optional[str] = None
    exception:    Optional[str] = None  # full traceback string
    timestamp:    float = field(default_factory=lambda: datetime.utcnow().timestamp())
    metadata:     dict = field(default_factory=dict)


@dataclass
class GoldenCase:
    id:           str               # UUID4
    span:         AgentSpan
    human_label:  bool              # True = pass, False = fail
    human_notes:  str
    difficulty:   Literal["easy", "medium", "hard", "adversarial"]
    created_at:   datetime
    reviewed_by:  str
```

---

## Rules

- These are **pure Python dataclasses** — no Pydantic, no SQLAlchemy here.
- `AgentSpan` is the central object passed through the entire pipeline.
- `ToolCall.timestamp` is a raw Unix float, not a `datetime`, for easy JSON serialization.
- `AgentSpan.failure_type` starts as `None` and is set by `FailureClassifier.classify()`.
- `GoldenCase` lives in `evaluator/` conceptually but the dataclass is defined here to avoid circular imports.

---

## Acceptance Criteria

- [ ] All three dataclasses instantiate with sensible defaults
- [ ] `AgentSpan` with no `tool_calls` uses an empty list (not `None`)
- [ ] `ToolCall` with `error=None` and `result=None` is valid
- [ ] No circular import issues when importing from `agentprobe.models`
