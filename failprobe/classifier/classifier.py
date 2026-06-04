"""The rule-based :class:`FailureClassifier`.

Classifies an :class:`~failprobe.models.AgentSpan` into a
:class:`~failprobe.classifier.taxonomy.FailureType` using only synchronous
Python logic — no LLM calls, no network, no I/O. Designed to complete in <10ms
at the 99th percentile.
"""

from typing import Any

from failprobe.classifier.rules.context import detect_context_overflow
from failprobe.classifier.rules.loop_detector import detect_loop
from failprobe.classifier.rules.tool_errors import classify_tool_error
from failprobe.classifier.taxonomy import FailureType
from failprobe.config import get_config
from failprobe.models import AgentSpan

REFUSAL_PATTERNS = [
    "i cannot help",
    "i can't help",
    "i am unable to",
    "i'm unable to",
    "i must decline",
    "i cannot assist",
    "i won't be able to",
]


def _is_refusal(output: Any) -> bool:
    """Return whether ``output`` is text matching a known refusal phrase."""
    if not isinstance(output, str):
        return False
    text = output.lower()
    return any(p in text for p in REFUSAL_PATTERNS)


class FailureClassifier:
    """Assigns a :class:`FailureType` to an :class:`AgentSpan` via fixed rules.

    Stateless and synchronous; instances are cheap to create and reuse.
    """

    def classify(self, span: AgentSpan) -> tuple[FailureType | None, str]:
        """Classify ``span`` into a failure type using the fixed priority order.

        The checks run in this exact order, stopping at the first match:

        1. Exception containing ``"TimeoutError"`` → ``TIMEOUT``
        2. Any other exception → ``EXCEPTION``
        3. Repetition loop in ``tool_calls`` → ``INFINITE_LOOP``
        4. A tool call reporting an error → tool-error subclassification
        5. Token count over threshold → ``CONTEXT_OVERFLOW``
        6. Refusal phrase in output → ``REFUSED``
        7. Unsuccessful with a "partial" message → ``PARTIAL_SUCCESS``
        8. Unsuccessful → ``TASK_FAILED``
        9. Otherwise → ``(None, "success")``

        Args:
            span: The captured agent run to classify.

        Returns:
            ``(FailureType, explanation)`` for a failure, or ``(None,
            "success")`` when no failure is detected.
        """
        config = get_config()

        # 1 & 2: system-level exceptions take top priority over everything else.
        if span.exception:
            if "TimeoutError" in span.exception:
                return (FailureType.TIMEOUT, "Run raised a TimeoutError.")
            return (FailureType.EXCEPTION, "Run raised an unhandled exception.")

        # 3: repetitive tool-call loop.
        is_loop, loop_msg = detect_loop(span.tool_calls, config.loop_threshold)
        if is_loop:
            return (FailureType.INFINITE_LOOP, loop_msg)

        # 4: a failing tool call → subclassify its error string.
        for tc in span.tool_calls:
            if tc.error:
                return (
                    classify_tool_error(tc.error),
                    f"Tool '{tc.tool_name}' failed: {tc.error}",
                )

        # 5: token/context overflow.
        if detect_context_overflow(span.tokens_used, config.token_overflow_threshold):
            return (
                FailureType.CONTEXT_OVERFLOW,
                f"Token count {span.tokens_used} exceeded threshold "
                f"{config.token_overflow_threshold}.",
            )

        # 6: explicit refusal in the output text.
        if _is_refusal(span.output):
            return (FailureType.REFUSED, "Output matched a refusal pattern.")

        # 7 & 8: generic unsuccessful outcomes.
        if span.success is False:
            if span.failure_msg and "partial" in span.failure_msg.lower():
                return (FailureType.PARTIAL_SUCCESS, span.failure_msg)
            return (FailureType.TASK_FAILED, span.failure_msg or "Run did not succeed.")

        # 9: no failure detected.
        return (None, "success")
