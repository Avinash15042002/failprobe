"""Canonical failure taxonomy for FailProbe.

This module is the single source of truth for the 15 failure categories used
across the classifier, storage, API, and dashboard. It contains only the
:class:`FailureType` enum and the :data:`FAILURE_DESCRIPTIONS` mapping — no
classification logic, no LLM calls, no network access.
"""

from enum import Enum


class FailureType(Enum):
    """Enumerates every failure category FailProbe can assign to a run.

    The string value of each member is the stable identifier persisted to
    storage and emitted over the API. Resolve a member from its value with
    ``FailureType("wrong_tool")``.
    """

    # Tool-use failures
    WRONG_TOOL = "wrong_tool"
    BAD_PARAMS = "bad_params"
    MISSING_TOOL = "missing_tool"
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_API_ERROR = "tool_api_error"

    # Reasoning failures
    HALLUCINATED_CALL = "hallucinated_call"
    CONTEXT_OVERFLOW = "context_overflow"
    INFINITE_LOOP = "infinite_loop"
    WRONG_FORMAT = "wrong_format"

    # Output failures
    TASK_FAILED = "task_failed"
    PARTIAL_SUCCESS = "partial_success"
    REFUSED = "refused"

    # System failures
    EXCEPTION = "exception"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


FAILURE_DESCRIPTIONS: dict[FailureType, str] = {
    FailureType.WRONG_TOOL: "Agent called a semantically irrelevant tool for the task.",
    FailureType.BAD_PARAMS: "Tool rejected the call due to invalid or missing parameters.",
    FailureType.MISSING_TOOL: "Agent attempted to call a tool that was not registered in the allowed toolset.",
    FailureType.TOOL_TIMEOUT: "A tool call exceeded its timeout limit.",
    FailureType.TOOL_API_ERROR: "A tool returned an HTTP or API-level error (4xx/5xx).",
    FailureType.HALLUCINATED_CALL: "Agent called a tool that does not exist in any available toolset.",
    FailureType.CONTEXT_OVERFLOW: "Token count exceeded the context window threshold mid-run.",
    FailureType.INFINITE_LOOP: "The same (tool, params) fingerprint was called repeatedly above the loop threshold.",
    FailureType.WRONG_FORMAT: "Agent output did not match the expected schema or format.",
    FailureType.TASK_FAILED: "Run completed but the output is factually wrong or does not satisfy the task.",
    FailureType.PARTIAL_SUCCESS: "Some subtasks completed successfully but not all required ones.",
    FailureType.REFUSED: "The LLM declined to complete the task.",
    FailureType.EXCEPTION: "An unhandled Python exception was raised during the run.",
    FailureType.TIMEOUT: "The full agent run exceeded its wall-clock timeout.",
    FailureType.UNKNOWN: "Classifier could not determine the failure reason.",
}
