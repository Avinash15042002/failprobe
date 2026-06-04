"""Shared route helpers for reconstructing domain objects from ORM rows.

The judge and meta-evaluator operate on the in-memory
:class:`~agentprobe.models.AgentSpan` dataclass, but persisted runs live as
:class:`~agentprobe.storage.models.Run` rows plus their
:class:`~agentprobe.storage.models.ToolCallRecord` rows. This module bridges the
two so the eval and review routes don't duplicate the mapping. It is pure
transformation — no I/O.
"""

import json
from typing import Any

from agentprobe.models import AgentSpan, ToolCall
from agentprobe.storage.models import Run, ToolCallRecord


def maybe_json(raw: str | None) -> Any:
    """Decode a JSON-serialized column, falling back to the raw string.

    Run/tool payloads are stored as JSON text; older or hand-written rows may
    hold a bare string. A ``None`` input returns ``None``.
    """
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def span_from_run(run: Run, tool_calls: list[ToolCallRecord]) -> AgentSpan:
    """Rebuild an :class:`AgentSpan` from a :class:`Run` row and its tool calls.

    JSON-serialized payloads (input/output/params/result) are decoded; the
    timezone-aware ``timestamp`` columns are converted to Unix floats to match
    the dataclass representation.
    """
    return AgentSpan(
        run_id=run.id,
        agent_name=run.agent_name,
        input=maybe_json(run.input_text),
        output=maybe_json(run.output_text),
        duration_ms=run.duration_ms,
        tool_calls=[
            ToolCall(
                tool_name=record.tool_name,
                params=maybe_json(record.params) or {},
                result=maybe_json(record.result),
                duration_ms=record.duration_ms,
                error=record.error,
                timestamp=record.timestamp.timestamp(),
            )
            for record in tool_calls
        ],
        tokens_used=run.tokens_used,
        model=run.model,
        success=run.success,
        failure_type=run.failure_type,
        failure_msg=run.failure_msg,
        exception=run.exception,
    )
