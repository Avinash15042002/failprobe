"""Regression comparison route.

``POST /compare`` computes a statistically honest delta between a baseline and a
candidate set of runs for one metric (accuracy, judge score, or cost). All
statistics are delegated to the regression layer (``agentprobe/regression``) —
this route only fetches rows, projects them onto the chosen metric, and shapes
the response (Rule: the API embeds no statistical business logic).

Significance handling (Rule 4 — no delta without a significance verdict):

* ``accuracy`` (binary): McNemar's exact test on the positionally-paired
  outcomes (truncated to the shorter group) yields a ``p_value``.
* ``score`` / ``cost`` (continuous): ``stats.py`` offers no unpaired test, so
  ``p_value`` is ``None`` and ``significant`` is reported conservatively as
  "the two bootstrap CIs are disjoint".
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from agentprobe.regression.runner import COST_PER_1K_TOKENS
from agentprobe.regression.stats import bootstrap_ci, mcnemar_test
from agentprobe.storage import get_session
from agentprobe.storage.models import EvalResult, Run
from api.schemas import CompareRequest, CompareResponse

router = APIRouter(tags=["compare"])

_MIN_GROUP_SIZE = 5
_MIN_RELIABLE_N = 30


def _run_cost_usd(run: Run) -> float:
    """Estimate a run's USD cost from its tokens and model; 0.0 if unknown."""
    if not run.tokens_used or not run.model:
        return 0.0
    rate = COST_PER_1K_TOKENS.get(run.model)
    if rate is None:
        return 0.0
    return (run.tokens_used / 1000.0) * rate


async def _project(run_ids: list[str], metric: str) -> list[float]:
    """Fetch runs for ``run_ids`` and project them onto ``metric`` values."""
    async with get_session() as session:
        runs = (
            await session.execute(select(Run).where(Run.id.in_(run_ids)))
        ).scalars().all()
        by_id = {run.id: run for run in runs}

        scores: dict[str, float] = {}
        if metric == "score":
            eval_rows = (
                await session.execute(
                    select(EvalResult).where(EvalResult.run_id.in_(run_ids))
                )
            ).scalars().all()
            # Keep the most recent score per run (rows arrive oldest-first).
            for row in eval_rows:
                scores[row.run_id] = row.score

    values: list[float] = []
    for run_id in run_ids:
        run = by_id.get(run_id)
        if run is None:
            continue
        if metric == "accuracy":
            values.append(1.0 if run.success else 0.0)
        elif metric == "cost":
            values.append(_run_cost_usd(run))
        elif metric == "score" and run_id in scores:
            values.append(scores[run_id])
    return values


@router.post("/compare", response_model=CompareResponse)
async def compare(request: CompareRequest) -> CompareResponse:
    """Compare baseline vs. candidate runs on one metric with CI + significance."""
    if len(request.baseline_run_ids) < _MIN_GROUP_SIZE or (
        len(request.candidate_run_ids) < _MIN_GROUP_SIZE
    ):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "insufficient_data",
                "message": f"Each group needs at least {_MIN_GROUP_SIZE} runs.",
            },
        )

    baseline_vals = await _project(request.baseline_run_ids, request.metric)
    candidate_vals = await _project(request.candidate_run_ids, request.metric)

    if len(baseline_vals) < _MIN_GROUP_SIZE or len(candidate_vals) < _MIN_GROUP_SIZE:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "insufficient_data",
                "message": "Too few runs with the requested metric available.",
            },
        )

    baseline_mean = sum(baseline_vals) / len(baseline_vals)
    candidate_mean = sum(candidate_vals) / len(candidate_vals)
    baseline_ci = bootstrap_ci(baseline_vals)
    candidate_ci = bootstrap_ci(candidate_vals)

    p_value: Optional[float] = None
    if request.metric == "accuracy":
        paired = min(len(baseline_vals), len(candidate_vals))
        p_value, significant = mcnemar_test(
            [bool(v) for v in baseline_vals[:paired]],
            [bool(v) for v in candidate_vals[:paired]],
        )
    else:
        # Disjoint bootstrap CIs ⇒ a conservative "significant" verdict.
        significant = candidate_ci[1] < baseline_ci[0] or candidate_ci[0] > baseline_ci[1]

    warning: Optional[str] = None
    if min(len(baseline_vals), len(candidate_vals)) < _MIN_RELIABLE_N:
        warning = "small_sample_ci_may_be_unreliable"

    return CompareResponse(
        metric=request.metric,
        n_baseline=len(baseline_vals),
        n_candidate=len(candidate_vals),
        baseline_mean=baseline_mean,
        candidate_mean=candidate_mean,
        delta=candidate_mean - baseline_mean,
        baseline_ci=baseline_ci,
        candidate_ci=candidate_ci,
        p_value=p_value,
        significant=significant,
        warning=warning,
    )
