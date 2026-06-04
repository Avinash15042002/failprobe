"""Detect hallucinated tool calls — calls to tools outside the allowed set.

Pure membership checks — no LLM calls, no network, no I/O.
"""

from failprobe.models import ToolCall


def detect_hallucinated_calls(
    tool_calls: list[ToolCall],
    allowed_tools: list[str],
) -> tuple[bool, str]:
    """Detect tool calls that invoke a tool outside ``allowed_tools``.

    Args:
        tool_calls: The tool calls captured during the run.
        allowed_tools: The registered/allowed tool names. If empty or ``None``,
            detection is skipped and ``(False, "")`` is returned.

    Returns:
        ``(True, explanation)`` listing the hallucinated tool names, else
        ``(False, "")``.
    """
    if not allowed_tools:
        return (False, "")

    allowed = set(allowed_tools)
    hallucinated = [tc.tool_name for tc in tool_calls if tc.tool_name not in allowed]
    if hallucinated:
        unique = sorted(set(hallucinated))
        return (
            True,
            f"Called tool(s) not in the allowed set: {', '.join(unique)}.",
        )
    return (False, "")
