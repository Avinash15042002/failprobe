"""Individual rule functions used by the rule-based classifier.

Each rule is a pure, synchronous function — no LLM calls, no network, no I/O.
Only the names in ``__all__`` are part of the supported interface.
"""

from failprobe.classifier.rules.context import detect_context_overflow
from failprobe.classifier.rules.hallucination import detect_hallucinated_calls
from failprobe.classifier.rules.loop_detector import detect_loop
from failprobe.classifier.rules.tool_errors import classify_tool_error

__all__ = [
    "classify_tool_error",
    "detect_loop",
    "detect_hallucinated_calls",
    "detect_context_overflow",
]
