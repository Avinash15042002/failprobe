"""Detect repetitive tool-call loops within an agent run.

Pure Python fingerprinting — no LLM calls, no network, no I/O. This function
never raises: unhashable parameters fall back to a string fingerprint.
"""

from collections import Counter

from failprobe.models import ToolCall


def detect_loop(tool_calls: list[ToolCall], threshold: int) -> tuple[bool, str]:
    """Detect whether ``tool_calls`` exhibit a repetition loop.

    Two independent signals trigger a loop, checked in this order:

    1. Any ``(tool_name, params)`` fingerprint occurs ``>= threshold`` times.
    2. The last ``threshold`` calls share an identical ``tool_name`` regardless
       of params.

    The fingerprint is ``(tool_name, frozenset(params.items()))``; if ``params``
    contains unhashable values (or is not a mapping) it falls back to
    ``(tool_name, str(params))``. This function never raises.

    Args:
        tool_calls: The tool calls captured during the run, in order.
        threshold: Minimum repetition count that constitutes a loop. A
            non-positive threshold disables detection.

    Returns:
        ``(True, explanation)`` if a loop is detected, else ``(False, "")``.
    """
    if threshold <= 0 or len(tool_calls) < threshold:
        return (False, "")

    # Signal 1: identical (tool, params) fingerprint repeated >= threshold times.
    fingerprints: Counter = Counter()
    for tc in tool_calls:
        try:
            fingerprint = (tc.tool_name, frozenset(tc.params.items()))
        except (TypeError, AttributeError):
            fingerprint = (tc.tool_name, str(tc.params))
        fingerprints[fingerprint] += 1

    for (tool_name, _params), count in fingerprints.items():
        if count >= threshold:
            return (
                True,
                f"Tool '{tool_name}' called with identical params {count} times "
                f"(threshold {threshold}).",
            )

    # Signal 2: the last `threshold` calls all invoked the same tool.
    last_names = {tc.tool_name for tc in tool_calls[-threshold:]}
    if len(last_names) == 1:
        name = next(iter(last_names))
        return (
            True,
            f"Last {threshold} calls all invoked tool '{name}' "
            f"(threshold {threshold}).",
        )

    return (False, "")
