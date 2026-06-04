"""Canonical in-memory dataclasses shared across the AgentProbe pipeline.

These are pure Python ``dataclasses`` — not Pydantic schemas and not SQLAlchemy
ORM models. The ORM equivalents live in ``agentprobe/storage/models.py`` (Task 06).

``AgentSpan`` is the central object that flows from the ``@probe`` decorator
through the classifier, evaluator, and storage layers.

Note: ``failure_type`` is typed as ``Optional[str]`` here (not the
``FailureType`` enum) to keep this module free of any import from
``agentprobe/classifier/`` and thereby avoid a circular import. The classifier
sets it from the enum's string value.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Optional


@dataclass
class ToolCall:
    """A single tool invocation captured within an agent run.

    ``timestamp`` is a raw Unix float (not a ``datetime``) for easy JSON
    serialization. ``error`` is ``None`` on success.
    """

    tool_name: str
    params: dict
    result: Any
    duration_ms: float
    error: Optional[str]
    timestamp: float  # Unix timestamp


@dataclass
class AgentSpan:
    """A single end-to-end agent invocation and its observed outcome.

    Created by the ``@probe`` decorator. ``failure_type`` starts as ``None`` and
    is later populated by ``FailureClassifier.classify()`` with a failure-type
    string value.
    """

    run_id: str  # UUID4
    agent_name: str
    input: Any
    output: Any
    duration_ms: float
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_used: Optional[int] = None
    model: Optional[str] = None
    success: bool = True
    failure_type: Optional[str] = None
    failure_msg: Optional[str] = None
    exception: Optional[str] = None  # full traceback string
    timestamp: float = field(default_factory=lambda: datetime.utcnow().timestamp())
    metadata: dict = field(default_factory=dict)


@dataclass
class GoldenCase:
    """A human-labeled span used as ground truth for meta-evaluation.

    Defined here rather than in ``evaluator/`` to avoid circular imports.
    ``human_label`` is ``True`` for pass and ``False`` for fail.
    """

    id: str  # UUID4
    span: AgentSpan
    human_label: bool  # True = pass, False = fail
    human_notes: str
    difficulty: Literal["easy", "medium", "hard", "adversarial"]
    created_at: datetime
    reviewed_by: str
