"""Meta-evaluation: score the LLM judge against a human-labelled golden dataset.

This is FailProbe's headline feature. It answers *"how accurate is your
judge?"* — running the judge over every golden case, comparing its pass/fail
prediction against the human label, and reporting accuracy, precision, recall,
F1, and a bootstrapped confidence interval so the result can be stated honestly
as e.g. *"91% accurate ±4% on 100 labelled cases."*

Statistical-honesty rules (spec §2.5) are enforced here: with fewer than 10
cases the CI is skipped (``warning="too_few_cases"``); with fewer than 30 the CI
is computed but flagged unreliable (``warning="ci_may_be_unreliable"``).

The judge call is the only external dependency and is injected via the
module-level :func:`judge_run` name, which tests monkeypatch — no real API calls
are made under test.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional

from failprobe.evaluator.judge import judge_run
from failprobe.models import GoldenCase
from failprobe.regression.stats import bootstrap_ci

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# Below this many cases a bootstrap CI is statistically meaningless — skip it.
_MIN_CASES_FOR_CI = 10
# Below this many cases the CI is computed but should be treated with caution.
_MIN_CASES_FOR_RELIABLE_CI = 30


@dataclass
class MetaEvalReport:
    """The outcome of scoring a judge against a golden dataset.

    ``confidence_interval`` is a 95% bootstrap CI on ``judge_accuracy``. When
    ``warning`` is ``"too_few_cases"`` the CI is degenerate (the point estimate
    repeated) because it was skipped; ``"ci_may_be_unreliable"`` means the CI was
    computed but the sample is small (n < 30).
    """

    judge_accuracy: float
    precision: float
    recall: float
    f1: float
    confidence_interval: tuple[float, float]
    n_cases: int
    n_correct: int
    disagreement_rate: float
    generated_at: datetime
    warning: Optional[str] = None


@lru_cache(maxsize=1)
def default_rubric() -> str:
    """Load and cache the default scoring rubric from ``prompts/rubric.txt``."""
    return (_PROMPTS_DIR / "rubric.txt").read_text(encoding="utf-8")


async def run_meta_eval(
    golden_dataset: list[GoldenCase],
    judge_model: str,
    threshold: float = 0.5,
) -> MetaEvalReport:
    """Score the judge against ``golden_dataset`` and return a :class:`MetaEvalReport`.

    For each case the judge is run and its ``score >= threshold`` is taken as the
    predicted pass/fail label, then compared against the human label. Precision,
    recall, and F1 treat ``True`` (pass) as the positive class. Accuracy gets a
    95% bootstrap CI subject to the small-sample rules described in the module
    docstring.

    Args:
        golden_dataset: Human-labelled cases to evaluate against.
        judge_model: Model identifier passed to :func:`judge_run`.
        threshold: Score at or above which a run is predicted to pass.

    Returns:
        A :class:`MetaEvalReport` summarizing judge accuracy and agreement.
    """
    n_cases = len(golden_dataset)
    if n_cases == 0:
        return MetaEvalReport(
            judge_accuracy=0.0,
            precision=0.0,
            recall=0.0,
            f1=0.0,
            confidence_interval=(0.0, 0.0),
            n_cases=0,
            n_correct=0,
            disagreement_rate=0.0,
            generated_at=_now(),
            warning="too_few_cases",
        )

    rubric = default_rubric()
    correctness: list[bool] = []
    true_pos = false_pos = false_neg = 0

    for case in golden_dataset:
        result = await judge_run(case.span, rubric, model=judge_model)
        predicted = result.score >= threshold
        actual = case.human_label
        correctness.append(predicted == actual)
        if predicted and actual:
            true_pos += 1
        elif predicted and not actual:
            false_pos += 1
        elif not predicted and actual:
            false_neg += 1

    n_correct = sum(correctness)
    accuracy = n_correct / n_cases
    precision = true_pos / (true_pos + false_pos) if (true_pos + false_pos) else 0.0
    recall = true_pos / (true_pos + false_neg) if (true_pos + false_neg) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    if n_cases < _MIN_CASES_FOR_CI:
        confidence_interval = (accuracy, accuracy)
        warning: Optional[str] = "too_few_cases"
    else:
        confidence_interval = bootstrap_ci(correctness)
        warning = "ci_may_be_unreliable" if n_cases < _MIN_CASES_FOR_RELIABLE_CI else None

    return MetaEvalReport(
        judge_accuracy=accuracy,
        precision=precision,
        recall=recall,
        f1=f1,
        confidence_interval=confidence_interval,
        n_cases=n_cases,
        n_correct=n_correct,
        disagreement_rate=1.0 - accuracy,
        generated_at=_now(),
        warning=warning,
    )


def _now() -> datetime:
    """Return the current time as a timezone-aware UTC ``datetime``."""
    return datetime.now(timezone.utc)
