"""Golden-dataset management: load, save, and summarize human-labelled cases.

A *golden dataset* is the human-labelled ground truth that the meta-evaluator
(``meta_eval.py``) scores the LLM judge against. Cases are persisted as JSONL —
one :class:`~failprobe.models.GoldenCase` JSON object per line — at
:data:`DEFAULT_GOLDEN_PATH` in the working directory by default.

This module owns serialization of the nested ``GoldenCase → AgentSpan →
ToolCall`` structure. Per the evaluator's layer ownership it touches only the
filesystem (golden dataset I/O); it performs no span capture, classification,
or LLM calls.
"""

import json
import os
from datetime import datetime, timezone

from failprobe.models import AgentSpan, GoldenCase, ToolCall

DEFAULT_GOLDEN_PATH = "failprobe_golden.jsonl"


def _toolcall_to_dict(call: ToolCall) -> dict:
    """Serialize a :class:`ToolCall` to a JSON-safe dict."""
    return {
        "tool_name": call.tool_name,
        "params": call.params,
        "result": call.result,
        "duration_ms": call.duration_ms,
        "error": call.error,
        "timestamp": call.timestamp,
    }


def _span_to_dict(span: AgentSpan) -> dict:
    """Serialize an :class:`AgentSpan` (with its tool calls) to a JSON-safe dict."""
    return {
        "run_id": span.run_id,
        "agent_name": span.agent_name,
        "input": span.input,
        "output": span.output,
        "duration_ms": span.duration_ms,
        "tool_calls": [_toolcall_to_dict(call) for call in span.tool_calls],
        "tokens_used": span.tokens_used,
        "model": span.model,
        "success": span.success,
        "failure_type": span.failure_type,
        "failure_msg": span.failure_msg,
        "exception": span.exception,
        "timestamp": span.timestamp,
        "metadata": span.metadata,
    }


def _case_to_dict(case: GoldenCase) -> dict:
    """Serialize a :class:`GoldenCase` to a JSON-safe dict (datetime → ISO 8601)."""
    return {
        "id": case.id,
        "span": _span_to_dict(case.span),
        "human_label": case.human_label,
        "human_notes": case.human_notes,
        "difficulty": case.difficulty,
        "created_at": case.created_at.isoformat(),
        "reviewed_by": case.reviewed_by,
    }


def _span_from_dict(data: dict) -> AgentSpan:
    """Rebuild an :class:`AgentSpan` from its serialized dict form."""
    return AgentSpan(
        run_id=data["run_id"],
        agent_name=data["agent_name"],
        input=data.get("input"),
        output=data.get("output"),
        duration_ms=data["duration_ms"],
        tool_calls=[
            ToolCall(
                tool_name=tc["tool_name"],
                params=tc.get("params", {}),
                result=tc.get("result"),
                duration_ms=tc["duration_ms"],
                error=tc.get("error"),
                timestamp=tc.get("timestamp", 0.0),
            )
            for tc in data.get("tool_calls", [])
        ],
        tokens_used=data.get("tokens_used"),
        model=data.get("model"),
        success=data.get("success", True),
        failure_type=data.get("failure_type"),
        failure_msg=data.get("failure_msg"),
        exception=data.get("exception"),
        timestamp=data.get("timestamp", 0.0),
        metadata=data.get("metadata", {}),
    )


def _case_from_dict(data: dict) -> GoldenCase:
    """Rebuild a :class:`GoldenCase` from its serialized dict form."""
    return GoldenCase(
        id=data["id"],
        span=_span_from_dict(data["span"]),
        human_label=data["human_label"],
        human_notes=data.get("human_notes", ""),
        difficulty=data["difficulty"],
        created_at=datetime.fromisoformat(data["created_at"]),
        reviewed_by=data.get("reviewed_by", ""),
    )


class GoldenDatasetManager:
    """Load, persist, and summarize a JSONL golden dataset.

    The manager holds the active dataset path and an in-memory list of cases.
    If the file already exists at construction time it is loaded eagerly, so
    :meth:`add_case` and :meth:`get_stats` work without an explicit
    :meth:`load` call.
    """

    def __init__(self, path: str = DEFAULT_GOLDEN_PATH) -> None:
        """Create a manager bound to ``path``, loading existing cases if present."""
        self.path: str = path
        self.cases: list[GoldenCase] = []
        if os.path.exists(path):
            self.load(path)

    def load(self, path: str) -> list[GoldenCase]:
        """Load cases from the JSONL file at ``path`` and make it the active path.

        A missing file is treated as an empty dataset (returns ``[]``). Blank
        lines are skipped.
        """
        cases: list[GoldenCase] = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if line:
                        cases.append(_case_from_dict(json.loads(line)))
        self.path = path
        self.cases = cases
        return cases

    def save(self, cases: list[GoldenCase], path: str) -> None:
        """Write ``cases`` to ``path`` as JSONL and make it the active dataset."""
        with open(path, "w", encoding="utf-8") as handle:
            for case in cases:
                handle.write(json.dumps(_case_to_dict(case)) + "\n")
        self.path = path
        self.cases = list(cases)

    def add_case(self, case: GoldenCase) -> None:
        """Append ``case`` to the in-memory dataset and persist to the active path."""
        self.cases.append(case)
        self.save(self.cases, self.path)

    def get_stats(self) -> dict:
        """Return summary statistics for the loaded dataset.

        Returns:
            A dict with ``n_cases`` (int), ``pass_rate`` (fraction labelled
            pass), ``difficulty_distribution`` (count per difficulty), and
            ``last_updated`` (ISO 8601 file mtime, or ``None`` if unsaved).
        """
        n_cases = len(self.cases)
        n_pass = sum(1 for case in self.cases if case.human_label)
        distribution: dict[str, int] = {}
        for case in self.cases:
            distribution[case.difficulty] = distribution.get(case.difficulty, 0) + 1
        last_updated: str | None = None
        if os.path.exists(self.path):
            mtime = os.path.getmtime(self.path)
            last_updated = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        return {
            "n_cases": n_cases,
            "pass_rate": (n_pass / n_cases) if n_cases else 0.0,
            "difficulty_distribution": distribution,
            "last_updated": last_updated,
        }
