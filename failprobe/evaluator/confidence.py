"""Low-confidence flagging: decide which judged runs need human review.

A run is routed to the human-review queue when the judge is unsure of itself.
This module is pure decision logic over a :class:`~failprobe.evaluator.judge.JudgeResult`
— no I/O. The caller (the API eval route) is responsible for writing flagged
runs to the ``review_queue`` table.
"""

from failprobe.evaluator.judge import JudgeResult

CONFIDENCE_THRESHOLD = 0.6

# Scores in this inclusive band are too close to the pass/fail boundary to trust.
_AMBIGUOUS_SCORE_LOW = 0.4
_AMBIGUOUS_SCORE_HIGH = 0.6


def should_flag_for_review(result: JudgeResult) -> bool:
    """Return ``True`` if ``result`` should be added to the human-review queue.

    A run is flagged when either signal indicates the judge is unreliable here:

    - self-reported ``confidence`` below :data:`CONFIDENCE_THRESHOLD` (0.6), or
    - a ``score`` in the ambiguous band ``[0.4, 0.6]`` straddling the pass/fail
      boundary.

    Args:
        result: The judge's evaluation of a single run.

    Returns:
        Whether the run warrants human review.
    """
    return (
        result.confidence < CONFIDENCE_THRESHOLD
        or _AMBIGUOUS_SCORE_LOW <= result.score <= _AMBIGUOUS_SCORE_HIGH
    )
