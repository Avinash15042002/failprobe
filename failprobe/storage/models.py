"""SQLAlchemy 2.0 ORM models for FailProbe persistence.

These are the on-disk representations of the in-memory dataclasses in
``failprobe/models.py``. The mapping is intentionally lossy in one direction:
nested structures (input/output payloads, tags, params) are stored as
JSON-serialized strings rather than relational columns, keeping the schema flat
and portable across SQLite (dev) and PostgreSQL (prod).

All primary keys are UUID4 strings. All ``datetime`` columns are timezone-aware
(``DateTime(timezone=True)``). This module contains only ORM models and the
declarative ``Base`` — no engine, session, or business logic (those live in
``db.py``).
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all FailProbe ORM models.

    Alembic's migration environment imports this class and uses
    ``Base.metadata`` as the autogenerate target.
    """


def _new_uuid() -> str:
    """Return a fresh UUID4 as a string, for use as a default primary key."""
    return str(uuid4())


def _utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC ``datetime``."""
    return datetime.now(timezone.utc)


class Run(Base):
    """A single end-to-end agent invocation persisted from an ``AgentSpan``."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    agent_name: Mapped[str] = mapped_column(String(255))
    input_text: Mapped[str] = mapped_column(Text)
    output_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean)
    failure_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    failure_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    exception: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ToolCallRecord(Base):
    """A single tool invocation captured within a :class:`Run`."""

    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"))
    tool_name: Mapped[str] = mapped_column(String(255))
    params: Mapped[str] = mapped_column(Text)
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class EvalResult(Base):
    """An LLM-judge (and optionally human) evaluation of a :class:`Run`."""

    __tablename__ = "eval_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"))
    judge_model: Mapped[str] = mapped_column(String(255))
    score: Mapped[float] = mapped_column(Float)
    reasoning: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    human_label: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    human_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RegressionBaseline(Base):
    """A frozen set of aggregate metrics used as a regression comparison point."""

    __tablename__ = "regression_baselines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    name: Mapped[str] = mapped_column(String(255))
    metrics: Mapped[str] = mapped_column(Text)
    n_runs: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ReviewQueueItem(Base):
    """A run flagged by low-confidence judging and queued for human review.

    Created when :func:`failprobe.evaluator.should_flag_for_review` fires for a
    judged run. ``reviewed`` flips to ``True`` once a human submits a label,
    which also promotes the run into the golden dataset.
    """

    __tablename__ = "review_queue"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"))
    reason: Mapped[str] = mapped_column(Text)
    judge_score: Mapped[float] = mapped_column(Float)
    judge_confidence: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
