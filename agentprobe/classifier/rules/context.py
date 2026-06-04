"""Detect context-window token overflow.

Pure numeric comparison — no LLM calls, no network, no I/O.
"""


def detect_context_overflow(tokens_used: int | None, threshold: int) -> bool:
    """Return whether ``tokens_used`` exceeds the overflow ``threshold``.

    Args:
        tokens_used: Tokens consumed during the run, or ``None`` if unknown.
        threshold: The token-overflow threshold.

    Returns:
        ``True`` if ``tokens_used`` is known and strictly greater than
        ``threshold``, else ``False``.
    """
    if tokens_used is None:
        return False
    return tokens_used > threshold
