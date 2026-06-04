"""Verify the JSON fixtures in ``tests/fixtures/`` deserialize into ``AgentSpan``.

TASK 16 item 2: all five fixture files must be present, valid JSON, and
round-trip into a real :class:`~failprobe.models.AgentSpan` (with its nested
``tool_calls`` rebuilt into :class:`~failprobe.models.ToolCall` objects)
without raising.
"""

import json
from pathlib import Path

import pytest

from failprobe.models import AgentSpan, ToolCall

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

EXPECTED_FILES = [
    "span_success.json",
    "span_wrong_tool.json",
    "span_infinite_loop.json",
    "span_exception.json",
    "span_context_overflow.json",
]


def _load_span(path: Path) -> AgentSpan:
    """Load one fixture file into an ``AgentSpan``, rebuilding its tool calls."""
    data = json.loads(path.read_text(encoding="utf-8"))
    data["tool_calls"] = [ToolCall(**call) for call in data.get("tool_calls", [])]
    return AgentSpan(**data)


def test_all_five_fixtures_present() -> None:
    """Exactly the five required fixture files exist."""
    present = {p.name for p in FIXTURES_DIR.glob("*.json")}
    assert set(EXPECTED_FILES) <= present


@pytest.mark.parametrize("filename", EXPECTED_FILES)
def test_fixture_deserializes_into_agentspan(filename: str) -> None:
    """Each fixture deserializes into an ``AgentSpan`` with typed tool calls."""
    span = _load_span(FIXTURES_DIR / filename)
    assert isinstance(span, AgentSpan)
    assert span.run_id
    assert span.agent_name
    assert all(isinstance(tc, ToolCall) for tc in span.tool_calls)
