"""Statistical primitives for the regression layer.

This module owns FailProbe's statistical-honesty rules (spec §5.5, Rule 4): no
metric is ever reported without a confidence interval, and no drop is ever called
a regression unless it is both above threshold *and* statistically significant.

It provides three pure functions:

* :func:`bootstrap_ci` — a percentile bootstrap confidence interval for the mean
  (numpy only). Reused by the meta-evaluator (TASK 13) for judge-accuracy CIs.
* :func:`mcnemar_test` — McNemar's exact test for two paired binary outcome
  vectors (before vs. after on the same cases).
* :func:`is_regression` — the gate that decides whether an accuracy drop is a
  real regression.

This module performs pure computation — no I/O, no network, no DB.

Note on McNemar's implementation: the V2 checklist says to use
``scipy.stats.mcnemar``, but that function does not exist in any released SciPy
(McNemar's test lives in ``statsmodels``, which is not a dependency). We instead
compute McNemar's *exact* test directly from the discordant pair counts using
:func:`scipy.stats.binomtest`, which is the canonical exact form of the test.
"""

import numpy as np
from scipy.stats import binomtest


def bootstrap_ci(
    data: list[bool] | list[float],
    n_resamples: int = 1000,
    ci: float = 0.95,
) -> tuple[float, float]:
    """Estimate a percentile bootstrap confidence interval for the mean.

    Resamples ``data`` with replacement ``n_resamples`` times, takes the mean of
    each resample, and returns the empirical ``ci`` quantile interval of those
    means. Booleans are treated as ``1.0``/``0.0`` so accuracy data (a list of
    correct/incorrect flags) yields a CI on the accuracy.

    Args:
        data: Observations to resample (booleans or floats). Empty input yields
            ``(0.0, 0.0)``.
        n_resamples: Number of bootstrap resamples to draw.
        ci: Central confidence mass, e.g. ``0.95`` for a 95% interval.

    Returns:
        The ``(lower, upper)`` bounds of the confidence interval.
    """
    if not data:
        return (0.0, 0.0)
    arr = np.asarray(data, dtype=float)
    n = len(arr)
    means = [float(np.mean(np.random.choice(arr, n, replace=True))) for _ in range(n_resamples)]
    alpha = (1.0 - ci) / 2.0
    return (float(np.quantile(means, alpha)), float(np.quantile(means, 1.0 - alpha)))


def mcnemar_test(
    before: list[bool],
    after: list[bool],
) -> tuple[float, bool]:
    """Run McNemar's exact test on two paired binary outcome vectors.

    McNemar's test asks whether the *change* between two paired binary
    measurements (here: each case's pass/fail before vs. after a code change) is
    statistically significant. Only the **discordant** pairs carry information:

    * ``b`` — cases that passed before but fail after (regressions),
    * ``c`` — cases that failed before but pass after (improvements).

    Under the null hypothesis "the change had no effect", each discordant pair is
    equally likely to go either way, so ``b`` follows a Binomial(``b + c``, 0.5)
    distribution. The exact two-sided p-value is therefore a binomial test on
    ``min(b, c)`` successes out of ``b + c`` discordant trials at ``p = 0.5``.
    Concordant pairs (both pass or both fail) are ignored — they say nothing
    about whether the change mattered.

    When there are no discordant pairs (``b + c == 0``, e.g. identical vectors)
    the test is undefined; we return ``(1.0, False)`` — no evidence of change.

    Args:
        before: Per-case pass/fail outcomes before the change.
        after: Per-case pass/fail outcomes after the change. Must be the same
            length as ``before`` (the vectors are paired by position).

    Returns:
        ``(p_value, is_significant)`` where ``is_significant`` is ``p < 0.05``.

    Raises:
        ValueError: If ``before`` and ``after`` have different lengths.
    """
    if len(before) != len(after):
        raise ValueError(
            f"paired vectors must be equal length: {len(before)} != {len(after)}"
        )
    b = sum(1 for prev, curr in zip(before, after) if prev and not curr)
    c = sum(1 for prev, curr in zip(before, after) if not prev and curr)
    n_discordant = b + c
    if n_discordant == 0:
        return (1.0, False)
    p_value = float(
        binomtest(min(b, c), n_discordant, 0.5, alternative="two-sided").pvalue
    )
    return (p_value, p_value < 0.05)


def is_regression(
    baseline: float,
    current: float,
    ci: tuple[float, float],
    threshold: float = 0.05,
) -> bool:
    """Decide whether an accuracy drop is a real regression.

    A regression is flagged only when **both** conditions hold (Rule 4 — raw
    deltas without significance are prohibited):

    1. **Magnitude.** The drop exceeds the threshold: ``current - baseline <
       -threshold``.
    2. **Significance.** The entire confidence interval of the current accuracy
       lies below the baseline: ``ci_upper < baseline``. Equivalently, the
       implied confidence interval of the *delta* ``(ci_lower - baseline,
       ci_upper - baseline)`` does not cross zero — its upper bound is negative.
       If the current CI still reaches up to (or past) the baseline, the drop is
       within noise and is **not** a regression.

    Args:
        baseline: The baseline (reference) accuracy.
        current: The newly measured accuracy.
        ci: The confidence interval of the *current* accuracy, as
            ``(lower, upper)``.
        threshold: Minimum absolute drop to consider, e.g. ``0.05`` for 5%.

    Returns:
        ``True`` if the drop is both large enough and statistically significant.
    """
    delta = current - baseline
    return delta < -threshold and ci[1] < baseline
