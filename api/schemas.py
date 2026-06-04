"""Pydantic v2 response and request schemas for the FailProbe REST API.

This module contains *only* API-facing data shapes and the small converters
that map a persisted ORM row (``failprobe.storage.models``) onto its public
schema. It holds no business logic and performs no I/O.

JSON-serialized ORM columns (``tags`` on :class:`Run`, ``params`` on
:class:`ToolCallRecord`) are decoded back into native ``dict`` values here so
that API consumers never see raw JSON strings.
"""

import json
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from failprobe.evaluator.meta_eval import MetaEvalReport
from failprobe.models import AgentSpan, GoldenCase, ToolCall
from failprobe.storage.models import EvalResult, Run, ToolCallRecord

_Difficulty = Literal["easy", "medium", "hard", "adversarial"]


def _loads(raw: Optional[str]) -> dict:
    """Decode a JSON object string into a ``dict``; empty/absent → ``{}``."""
    if not raw:
        return {}
    return json.loads(raw)


class ToolCallSchema(BaseModel):
    """A single tool invocation as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    tool_name: str
    params: dict
    result: Optional[str]
    duration_ms: float
    error: Optional[str]
    timestamp: datetime

    @classmethod
    def from_record(cls, record: ToolCallRecord) -> "ToolCallSchema":
        """Build a schema instance from a :class:`ToolCallRecord` ORM row."""
        return cls(
            id=record.id,
            run_id=record.run_id,
            tool_name=record.tool_name,
            params=_loads(record.params),
            result=record.result,
            duration_ms=record.duration_ms,
            error=record.error,
            timestamp=record.timestamp,
        )


class EvalResultSchema(BaseModel):
    """An LLM-judge (and optional human) evaluation as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    judge_model: str
    score: float
    reasoning: str
    confidence: float
    human_label: Optional[bool]
    human_notes: Optional[str]
    created_at: datetime

    @classmethod
    def from_orm_row(cls, row: EvalResult) -> "EvalResultSchema":
        """Build a schema instance from an :class:`EvalResult` ORM row."""
        return cls.model_validate(row)


class RunSchema(BaseModel):
    """A single agent run as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_name: str
    input_text: str
    output_text: Optional[str]
    duration_ms: float
    tokens_used: Optional[int]
    model: Optional[str]
    success: bool
    failure_type: Optional[str]
    failure_msg: Optional[str]
    exception: Optional[str]
    tags: dict
    created_at: datetime

    @classmethod
    def from_orm_row(cls, run: Run) -> "RunSchema":
        """Build a schema instance from a :class:`Run` ORM row."""
        return cls(
            id=run.id,
            agent_name=run.agent_name,
            input_text=run.input_text,
            output_text=run.output_text,
            duration_ms=run.duration_ms,
            tokens_used=run.tokens_used,
            model=run.model,
            success=run.success,
            failure_type=run.failure_type,
            failure_msg=run.failure_msg,
            exception=run.exception,
            tags=_loads(run.tags),
            created_at=run.created_at,
        )


class FailureBreakdownSchema(BaseModel):
    """Per-failure-type aggregate: occurrence count, description, and percent."""

    count: int
    description: str
    pct: float


class RunListResponse(BaseModel):
    """Paginated list of runs."""

    total: int
    runs: list[RunSchema]


class RunDetailResponse(BaseModel):
    """A single run together with its tool calls and (optional) evaluation."""

    run: RunSchema
    tool_calls: list[ToolCallSchema]
    eval_result: Optional[EvalResultSchema]


class TaxonomyResponse(BaseModel):
    """Failure-taxonomy breakdown across all recorded runs."""

    breakdown: dict[str, FailureBreakdownSchema]
    total_failures: int
    total_runs: int
    failure_rate: float


class FailureListResponse(BaseModel):
    """Paginated list of failed runs."""

    total: int
    failures: list[RunSchema]


class EvalRunRequest(BaseModel):
    """Request body for ``POST /eval/run``."""

    run_id: str
    model: Optional[str] = None


class CompareRequest(BaseModel):
    """Request body for ``POST /compare`` (regression comparison, Phase 2)."""

    baseline_run_ids: list[str]
    candidate_run_ids: list[str]
    metric: Literal["accuracy", "score", "cost"]


class CompareResponse(BaseModel):
    """Result of ``POST /compare``: a statistically honest baseline-vs-candidate delta.

    ``p_value`` is populated for the binary ``accuracy`` metric (McNemar's test on
    the positionally-paired outcomes, truncated to the shorter group) and is
    ``None`` for continuous metrics, where ``significant`` falls back to whether
    the two bootstrap CIs are disjoint. ``warning`` flags a small sample
    (``n < 30``) whose CI should be treated with caution.
    """

    metric: Literal["accuracy", "score", "cost"]
    n_baseline: int
    n_candidate: int
    baseline_mean: float
    candidate_mean: float
    delta: float
    baseline_ci: tuple[float, float]
    candidate_ci: tuple[float, float]
    p_value: Optional[float]
    significant: bool
    warning: Optional[str] = None


class ReviewRequest(BaseModel):
    """Request body for ``POST /review/{run_id}`` (human labeling, Phase 2)."""

    label: bool
    notes: str


class MetaEvalReportSchema(BaseModel):
    """Judge accuracy scored against the golden dataset (``GET /eval/judge-accuracy``)."""

    judge_accuracy: float
    precision: float
    recall: float
    f1: float
    confidence_interval: tuple[float, float]
    n_cases: int
    n_correct: int
    disagreement_rate: float
    generated_at: datetime
    warning: Optional[str] = None

    @classmethod
    def from_report(cls, report: MetaEvalReport) -> "MetaEvalReportSchema":
        """Build a schema instance from a :class:`MetaEvalReport` dataclass."""
        return cls(
            judge_accuracy=report.judge_accuracy,
            precision=report.precision,
            recall=report.recall,
            f1=report.f1,
            confidence_interval=report.confidence_interval,
            n_cases=report.n_cases,
            n_correct=report.n_correct,
            disagreement_rate=report.disagreement_rate,
            generated_at=report.generated_at,
            warning=report.warning,
        )


class ToolCallSpanSchema(BaseModel):
    """A tool call as embedded in an :class:`AgentSpanSchema`.

    Distinct from :class:`ToolCallSchema` (a persisted ``ToolCallRecord`` row):
    this mirrors the in-memory :class:`~failprobe.models.ToolCall` dataclass and
    carries no DB identifiers. ``result`` is ``Any`` per the dataclass contract.
    """

    tool_name: str
    params: dict
    result: Any = None
    duration_ms: float = 0.0
    error: Optional[str] = None
    timestamp: float = 0.0


class AgentSpanSchema(BaseModel):
    """An in-memory agent run, mirroring the :class:`~failprobe.models.AgentSpan` dataclass.

    ``input`` and ``output`` are ``Any`` because the underlying dataclass accepts
    arbitrary payloads.
    """

    run_id: str
    agent_name: str
    input: Any = None
    output: Any = None
    duration_ms: float = 0.0
    tool_calls: list[ToolCallSpanSchema] = []
    tokens_used: Optional[int] = None
    model: Optional[str] = None
    success: bool = True
    failure_type: Optional[str] = None
    failure_msg: Optional[str] = None
    exception: Optional[str] = None
    timestamp: float = 0.0
    metadata: dict = {}

    @classmethod
    def from_span(cls, span: AgentSpan) -> "AgentSpanSchema":
        """Build a schema instance from an :class:`AgentSpan` dataclass."""
        return cls(
            run_id=span.run_id,
            agent_name=span.agent_name,
            input=span.input,
            output=span.output,
            duration_ms=span.duration_ms,
            tool_calls=[
                ToolCallSpanSchema(
                    tool_name=call.tool_name,
                    params=call.params,
                    result=call.result,
                    duration_ms=call.duration_ms,
                    error=call.error,
                    timestamp=call.timestamp,
                )
                for call in span.tool_calls
            ],
            tokens_used=span.tokens_used,
            model=span.model,
            success=span.success,
            failure_type=span.failure_type,
            failure_msg=span.failure_msg,
            exception=span.exception,
            timestamp=span.timestamp,
            metadata=span.metadata,
        )

    def to_span(self) -> AgentSpan:
        """Build an :class:`AgentSpan` dataclass from this schema."""
        return AgentSpan(
            run_id=self.run_id,
            agent_name=self.agent_name,
            input=self.input,
            output=self.output,
            duration_ms=self.duration_ms,
            tool_calls=[
                ToolCall(
                    tool_name=call.tool_name,
                    params=call.params,
                    result=call.result,
                    duration_ms=call.duration_ms,
                    error=call.error,
                    timestamp=call.timestamp,
                )
                for call in self.tool_calls
            ],
            tokens_used=self.tokens_used,
            model=self.model,
            success=self.success,
            failure_type=self.failure_type,
            failure_msg=self.failure_msg,
            exception=self.exception,
            timestamp=self.timestamp,
            metadata=self.metadata,
        )


class GoldenCaseSchema(BaseModel):
    """A human-labelled golden case as returned by the API."""

    id: str
    span: AgentSpanSchema
    human_label: bool
    human_notes: str
    difficulty: _Difficulty
    created_at: datetime
    reviewed_by: str

    @classmethod
    def from_case(cls, case: GoldenCase) -> "GoldenCaseSchema":
        """Build a schema instance from a :class:`GoldenCase` dataclass."""
        return cls(
            id=case.id,
            span=AgentSpanSchema.from_span(case.span),
            human_label=case.human_label,
            human_notes=case.human_notes,
            difficulty=case.difficulty,
            created_at=case.created_at,
            reviewed_by=case.reviewed_by,
        )


class GoldenCaseCreate(BaseModel):
    """Request body for ``POST /golden``; ``id`` and ``created_at`` are generated."""

    span: AgentSpanSchema
    human_label: bool
    human_notes: str = ""
    difficulty: _Difficulty = "medium"
    reviewed_by: str = "human"

    def to_case(self) -> GoldenCase:
        """Build a fresh :class:`GoldenCase` with a new id and current timestamp."""
        return GoldenCase(
            id=str(uuid4()),
            span=self.span.to_span(),
            human_label=self.human_label,
            human_notes=self.human_notes,
            difficulty=self.difficulty,
            created_at=datetime.now(timezone.utc),
            reviewed_by=self.reviewed_by,
        )


class GoldenCasePatch(BaseModel):
    """Request body for ``PATCH /golden/{id}``; every field is optional."""

    human_label: Optional[bool] = None
    human_notes: Optional[str] = None
    difficulty: Optional[_Difficulty] = None
    reviewed_by: Optional[str] = None


class GoldenStatsSchema(BaseModel):
    """Summary statistics for the golden dataset."""

    n_cases: int
    pass_rate: float
    difficulty_distribution: dict[str, int]
    last_updated: Optional[str] = None


class GoldenListResponse(BaseModel):
    """``GET /golden`` response: all cases plus dataset statistics."""

    cases: list[GoldenCaseSchema]
    stats: GoldenStatsSchema


class ReviewQueueItemSchema(BaseModel):
    """A run flagged for human review (``ReviewQueueItem`` row)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    reason: str
    judge_score: float
    judge_confidence: float
    created_at: datetime
    reviewed: bool


class ReviewQueueEntrySchema(BaseModel):
    """A review-queue item joined with its originating run."""

    item: ReviewQueueItemSchema
    run: RunSchema


class ReviewQueueResponse(BaseModel):
    """``GET /review/queue`` response: unreviewed items with their runs."""

    cases: list[ReviewQueueEntrySchema]
