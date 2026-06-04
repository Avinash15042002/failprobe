"""Tests for the FailProbe rule-based classifier layer.

Covers the taxonomy, every ``FailureType``, the four rule sub-modules, the
``classify`` priority order, and edge cases. Factories come from ``conftest``.
"""

from conftest import make_span, make_tool_call

from failprobe.classifier import FAILURE_DESCRIPTIONS, FailureType
from failprobe.classifier.classifier import FailureClassifier
from failprobe.classifier.rules.context import detect_context_overflow
from failprobe.classifier.rules.hallucination import detect_hallucinated_calls
from failprobe.classifier.rules.loop_detector import detect_loop
from failprobe.classifier.rules.tool_errors import classify_tool_error
from failprobe.classifier.taxonomy import (
    FAILURE_DESCRIPTIONS as TAXONOMY_DESCRIPTIONS,
)
from failprobe.classifier.taxonomy import (
    FailureType as TaxonomyFailureType,
)

classifier = FailureClassifier()


# --------------------------------------------------------------------------- #
# Taxonomy
# --------------------------------------------------------------------------- #
def test_taxonomy() -> None:
    """The failure taxonomy has exactly 15 fully-described members."""
    # Exactly 15 categories, no more, no fewer.
    assert len(FailureType) == 15

    # Every member has a non-empty description; none missing.
    assert all(ft in FAILURE_DESCRIPTIONS for ft in FailureType)
    assert all(FAILURE_DESCRIPTIONS[ft] for ft in FailureType)

    # Value lookup resolves to the expected member.
    assert FailureType("wrong_tool") == FailureType.WRONG_TOOL

    # UNKNOWN has a non-empty description.
    assert FAILURE_DESCRIPTIONS[FailureType.UNKNOWN]

    # The package re-export is the same object as the submodule definition.
    assert FailureType is TaxonomyFailureType
    assert FAILURE_DESCRIPTIONS is TAXONOMY_DESCRIPTIONS


# --------------------------------------------------------------------------- #
# EXCEPTION
# --------------------------------------------------------------------------- #
def test_classifies_exception_runtime() -> None:
    """A non-timeout exception classifies as EXCEPTION."""
    span = make_span(exception="RuntimeError: API failed", success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.EXCEPTION


def test_classifies_exception_value_error() -> None:
    """A ValueError exception classifies as EXCEPTION."""
    span = make_span(exception="ValueError: bad value", success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.EXCEPTION


# --------------------------------------------------------------------------- #
# TIMEOUT
# --------------------------------------------------------------------------- #
def test_classifies_timeout_asyncio() -> None:
    """An asyncio.TimeoutError exception classifies as TIMEOUT."""
    span = make_span(exception="asyncio.TimeoutError: ...", success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.TIMEOUT


def test_classifies_timeout_plain() -> None:
    """Any exception containing TimeoutError classifies as TIMEOUT."""
    span = make_span(exception="TimeoutError: deadline exceeded", success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.TIMEOUT


# --------------------------------------------------------------------------- #
# INFINITE_LOOP
# --------------------------------------------------------------------------- #
def test_classifies_infinite_loop_identical_params() -> None:
    """Repeated identical (tool, params) fingerprints classify as INFINITE_LOOP."""
    calls = [make_tool_call("search", {"q": "weather"}) for _ in range(4)]
    span = make_span(tool_calls=calls, success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.INFINITE_LOOP


def test_classifies_infinite_loop_same_tool_name() -> None:
    """The last `threshold` calls sharing a tool name classify as INFINITE_LOOP."""
    calls = [
        make_tool_call("search", {"q": "a"}),
        make_tool_call("search", {"q": "b"}),
        make_tool_call("search", {"q": "c"}),
    ]
    span = make_span(tool_calls=calls, success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.INFINITE_LOOP


# --------------------------------------------------------------------------- #
# TOOL_TIMEOUT
# --------------------------------------------------------------------------- #
def test_classifies_tool_timeout_timed_out() -> None:
    """A 'timed out' tool error classifies as TOOL_TIMEOUT."""
    calls = [make_tool_call("fetch_url", {}, error="Connection timed out")]
    span = make_span(tool_calls=calls, success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.TOOL_TIMEOUT


def test_classifies_tool_timeout_keyword() -> None:
    """A 'timeout' tool error classifies as TOOL_TIMEOUT."""
    assert classify_tool_error("Request timeout after 30s") == FailureType.TOOL_TIMEOUT


# --------------------------------------------------------------------------- #
# BAD_PARAMS
# --------------------------------------------------------------------------- #
def test_classifies_bad_params_validation() -> None:
    """A validation tool error classifies as BAD_PARAMS."""
    calls = [make_tool_call("search", {}, error="validation error: query is required")]
    span = make_span(tool_calls=calls, success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.BAD_PARAMS


def test_classifies_bad_params_invalid() -> None:
    """An 'invalid argument' tool error classifies as BAD_PARAMS."""
    assert classify_tool_error("Invalid argument: foo") == FailureType.BAD_PARAMS


# --------------------------------------------------------------------------- #
# MISSING_TOOL
# --------------------------------------------------------------------------- #
def test_classifies_missing_tool_not_found() -> None:
    """A 'not found' tool error classifies as MISSING_TOOL."""
    calls = [make_tool_call("foo", {}, error="tool not found")]
    span = make_span(tool_calls=calls, success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.MISSING_TOOL


def test_classifies_missing_tool_does_not_exist() -> None:
    """A 'does not exist' tool error classifies as MISSING_TOOL."""
    assert classify_tool_error("Tool 'bar' does not exist") == FailureType.MISSING_TOOL


# --------------------------------------------------------------------------- #
# TOOL_API_ERROR
# --------------------------------------------------------------------------- #
def test_classifies_tool_api_error_status_code() -> None:
    """An HTTP 5xx tool error classifies as TOOL_API_ERROR."""
    calls = [make_tool_call("api", {}, error="500 internal server error")]
    span = make_span(tool_calls=calls, success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.TOOL_API_ERROR


def test_classifies_tool_api_error_empty() -> None:
    """An empty/None tool error defaults to TOOL_API_ERROR."""
    assert classify_tool_error("") == FailureType.TOOL_API_ERROR
    assert classify_tool_error(None) == FailureType.TOOL_API_ERROR


# --------------------------------------------------------------------------- #
# CONTEXT_OVERFLOW
# --------------------------------------------------------------------------- #
def test_classifies_context_overflow() -> None:
    """Token usage above the threshold classifies as CONTEXT_OVERFLOW."""
    span = make_span(tokens_used=150_000, success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.CONTEXT_OVERFLOW


def test_context_overflow_rule_none_and_bounds() -> None:
    """The overflow rule is None-safe and uses a strict greater-than."""
    assert detect_context_overflow(None, 100) is False
    assert detect_context_overflow(100, 100) is False
    assert detect_context_overflow(101, 100) is True


# --------------------------------------------------------------------------- #
# REFUSED
# --------------------------------------------------------------------------- #
def test_classifies_refused_cannot_help() -> None:
    """An 'I cannot help' output classifies as REFUSED."""
    span = make_span(output="I cannot help with that request.", success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.REFUSED


def test_classifies_refused_unable_to() -> None:
    """An 'I'm unable to' output classifies as REFUSED."""
    span = make_span(output="I'm unable to assist with this.", success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.REFUSED


# --------------------------------------------------------------------------- #
# PARTIAL_SUCCESS
# --------------------------------------------------------------------------- #
def test_classifies_partial_success() -> None:
    """An unsuccessful run with a 'partial' message classifies as PARTIAL_SUCCESS."""
    span = make_span(success=False, failure_msg="Completed partial result only")
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.PARTIAL_SUCCESS


def test_classifies_partial_success_case_insensitive() -> None:
    """The 'partial' match is case-insensitive."""
    span = make_span(success=False, failure_msg="PARTIAL completion")
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.PARTIAL_SUCCESS


# --------------------------------------------------------------------------- #
# TASK_FAILED
# --------------------------------------------------------------------------- #
def test_classifies_task_failed_no_message() -> None:
    """An unsuccessful run with no other signal classifies as TASK_FAILED."""
    span = make_span(success=False, output="wrong answer")
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.TASK_FAILED


def test_classifies_task_failed_with_message() -> None:
    """An unsuccessful run with a non-partial message classifies as TASK_FAILED."""
    span = make_span(success=False, failure_msg="Answer did not satisfy the task")
    ftype, msg = classifier.classify(span)
    assert ftype == FailureType.TASK_FAILED
    assert msg == "Answer did not satisfy the task"


# --------------------------------------------------------------------------- #
# HALLUCINATED_CALL (standalone rule — not part of the classify priority order)
# --------------------------------------------------------------------------- #
def test_detect_hallucinated_call_positive() -> None:
    """A call to a tool outside the allowed set is hallucinated."""
    calls = [make_tool_call("evil_tool", {})]
    is_hall, msg = detect_hallucinated_calls(calls, ["search", "fetch"])
    assert is_hall is True
    assert "evil_tool" in msg


def test_detect_hallucinated_call_empty_allowed() -> None:
    """Empty/None allowed_tools skips detection and returns (False, '')."""
    calls = [make_tool_call("anything", {})]
    assert detect_hallucinated_calls(calls, []) == (False, "")
    assert detect_hallucinated_calls(calls, None) == (False, "")


# --------------------------------------------------------------------------- #
# WRONG_TOOL (no TASK 05 rule emits this — reserved for the LLM judge, TASK 12)
# --------------------------------------------------------------------------- #
def test_wrong_tool_in_taxonomy() -> None:
    """WRONG_TOOL is a described member of the taxonomy."""
    assert FailureType.WRONG_TOOL in FAILURE_DESCRIPTIONS
    assert FAILURE_DESCRIPTIONS[FailureType.WRONG_TOOL]


def test_wrong_tool_value_mapping() -> None:
    """WRONG_TOOL resolves from its stable string value."""
    assert FailureType("wrong_tool") == FailureType.WRONG_TOOL


# --------------------------------------------------------------------------- #
# WRONG_FORMAT (no TASK 05 rule emits this — reserved for the LLM judge, TASK 12)
# --------------------------------------------------------------------------- #
def test_wrong_format_in_taxonomy() -> None:
    """WRONG_FORMAT is a described member of the taxonomy."""
    assert FailureType.WRONG_FORMAT in FAILURE_DESCRIPTIONS
    assert FAILURE_DESCRIPTIONS[FailureType.WRONG_FORMAT]


def test_wrong_format_value_mapping() -> None:
    """WRONG_FORMAT resolves from its stable string value."""
    assert FailureType("wrong_format") == FailureType.WRONG_FORMAT


# --------------------------------------------------------------------------- #
# UNKNOWN (fallback type — classify returns (None, 'success'), never UNKNOWN)
# --------------------------------------------------------------------------- #
def test_unknown_in_taxonomy() -> None:
    """UNKNOWN is a described member of the taxonomy."""
    assert FailureType.UNKNOWN in FAILURE_DESCRIPTIONS
    assert FAILURE_DESCRIPTIONS[FailureType.UNKNOWN]


def test_unknown_value_mapping() -> None:
    """UNKNOWN resolves from its stable string value."""
    assert FailureType("unknown") == FailureType.UNKNOWN


# --------------------------------------------------------------------------- #
# Success cases (3)
# --------------------------------------------------------------------------- #
def test_success_returns_none() -> None:
    """A successful span returns (None, 'success')."""
    span = make_span(success=True, output="The weather is 38C")
    ftype, msg = classifier.classify(span)
    assert ftype is None
    assert msg == "success"


def test_success_with_clean_tool_calls() -> None:
    """A successful span with error-free tool calls returns (None, 'success')."""
    calls = [make_tool_call("search", {"q": "x"}), make_tool_call("fetch", {"u": "y"})]
    span = make_span(success=True, tool_calls=calls)
    ftype, msg = classifier.classify(span)
    assert ftype is None
    assert msg == "success"


def test_success_under_token_threshold() -> None:
    """A successful span below the token threshold returns (None, 'success')."""
    span = make_span(success=True, tokens_used=1000)
    ftype, msg = classifier.classify(span)
    assert ftype is None
    assert msg == "success"


# --------------------------------------------------------------------------- #
# Edge cases (2)
# --------------------------------------------------------------------------- #
def test_priority_exception_over_loop() -> None:
    """Exception is caught before loop detection (priority order)."""
    calls = [make_tool_call("search", {"q": "x"}) for _ in range(5)]
    span = make_span(exception="RuntimeError", tool_calls=calls, success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.EXCEPTION  # not INFINITE_LOOP


def test_loop_detector_unhashable_params_never_raises() -> None:
    """Unhashable params fall back to str(params) without raising."""
    calls = [make_tool_call("search", {"q": ["a", "b"]}) for _ in range(4)]
    is_loop, msg = detect_loop(calls, threshold=3)
    assert is_loop is True
    assert msg
