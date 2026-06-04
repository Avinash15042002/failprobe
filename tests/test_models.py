"""Tests for the FailProbe core in-memory dataclasses."""

from datetime import datetime

from failprobe.models import AgentSpan, GoldenCase, ToolCall


def test_agentspan_defaults() -> None:
    """AgentSpan instantiates from required fields with sensible defaults."""
    span = AgentSpan(run_id="x", agent_name="a", input="q", output="r", duration_ms=10.0)
    assert span.tool_calls == []
    assert span.tokens_used is None
    assert span.model is None
    assert span.success is True
    assert span.failure_type is None
    assert span.failure_msg is None
    assert span.exception is None
    assert span.metadata == {}
    assert isinstance(span.timestamp, float)


def test_agentspan_mutable_defaults_are_independent() -> None:
    """The default tool_calls list and metadata dict are not shared."""
    a = AgentSpan(run_id="1", agent_name="a", input="i", output="o", duration_ms=1.0)
    b = AgentSpan(run_id="2", agent_name="a", input="i", output="o", duration_ms=1.0)
    a.tool_calls.append(
        ToolCall(tool_name="t", params={}, result=None, duration_ms=1.0, error=None, timestamp=0.0)
    )
    a.metadata["k"] = "v"
    assert b.tool_calls == []
    assert b.metadata == {}


def test_toolcall_allows_none_error_and_result() -> None:
    """ToolCall is valid with error=None and result=None."""
    tc = ToolCall(
        tool_name="search",
        params={"q": "x"},
        result=None,
        duration_ms=1.5,
        error=None,
        timestamp=0.0,
    )
    assert tc.error is None
    assert tc.result is None


def test_goldencase_instantiation() -> None:
    """GoldenCase wraps an AgentSpan with a human label and metadata."""
    span = AgentSpan(run_id="x", agent_name="a", input="q", output="r", duration_ms=10.0)
    case = GoldenCase(
        id="g1",
        span=span,
        human_label=True,
        human_notes="looks correct",
        difficulty="easy",
        created_at=datetime.utcnow(),
        reviewed_by="alice",
    )
    assert case.span is span
    assert case.human_label is True
    assert case.difficulty == "easy"


def test_failure_type_is_plain_string() -> None:
    """failure_type accepts a plain string value (no FailureType enum here)."""
    span = AgentSpan(run_id="x", agent_name="a", input="q", output="r", duration_ms=1.0)
    span.failure_type = "loop"
    assert span.failure_type == "loop"
