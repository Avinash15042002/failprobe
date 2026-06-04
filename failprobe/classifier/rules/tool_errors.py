"""Map a tool-call error string to a concrete tool-failure :class:`FailureType`.

Pure, case-insensitive string matching — no LLM calls, no network, no I/O. Used
by :class:`~failprobe.classifier.classifier.FailureClassifier` when a
:class:`~failprobe.models.ToolCall` reports an error.
"""

from failprobe.classifier.taxonomy import FailureType


def classify_tool_error(error: str) -> FailureType:
    """Classify a tool-call error string into a tool-failure type.

    Matching is case-insensitive and follows the fixed mapping table in
    ``TASK_05_failure_classifier.md``; the first matching category wins. HTTP
    status codes and any unrecognised error both fall through to
    :attr:`FailureType.TOOL_API_ERROR`.

    Args:
        error: The ``ToolCall.error`` string to classify. ``None`` or empty is
            treated as a generic API error.

    Returns:
        The :class:`FailureType` describing this error.
    """
    if not error:
        return FailureType.TOOL_API_ERROR

    text = error.lower()

    if "timeout" in text or "timed out" in text:
        return FailureType.TOOL_TIMEOUT
    if (
        "not found" in text
        or "no tool" in text
        or "undefined" in text
        or "does not exist" in text
    ):
        return FailureType.MISSING_TOOL
    if (
        "invalid" in text
        or "missing" in text
        or "required" in text
        or "type error" in text
        or "validation" in text
    ):
        return FailureType.BAD_PARAMS

    # HTTP status codes (4xx/5xx) and anything else map to a generic API error.
    return FailureType.TOOL_API_ERROR
