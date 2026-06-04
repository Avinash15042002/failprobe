"""Shared test fixtures and factories for the AgentProbe test suite.

``make_span`` and ``make_tool_call`` are the canonical factories used across
``test_classifier.py`` and later test modules (spec: TASK_16_test_suite.md).
"""

from agentprobe.models import AgentSpan, ToolCall


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
    """Factory for creating test ToolCall objects with sane defaults."""
    return ToolCall(
        tool_name=tool_name,
        params=params,
        result=None,
        duration_ms=50.0,
        error=error,
        timestamp=0.0,
    )
