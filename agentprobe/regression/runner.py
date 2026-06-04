"""Regression test-suite runner.

Loads a YAML suite, runs every case against a dynamically imported agent
function, scores each case pass/fail, and (when a baseline exists) decides
whether accuracy has regressed in a statistically significant way.

Design notes:

* **Statistical honesty (Rule 4 / Rule 10).** A drop is only a *regression* —
  and the process only exits non-zero — when the accuracy drop exceeds the
  suite's ``accuracy_drop_max`` threshold **and** McNemar's test on the paired
  per-case outcomes is significant (p < 0.05). A drop over threshold that is not
  significant produces a stderr warning and exit code 0.
* **Undecorated invocation.** Cases are scored by calling the agent's
  *undecorated* function (via ``functools.wraps``'s ``__wrapped__``) with our own
  ``_probe_collector``. The ``@probe`` wrapper deliberately overwrites any
  caller-supplied collector with its own and emits spans fire-and-forget to the
  DB, neither of which the runner can use for synchronous scoring — so the
  runner evaluates the raw function directly and injects its own collector.
* **Layering.** This module owns orchestration and cost arithmetic only. All
  statistics live in ``stats.py``; failure labelling reuses the rule-based
  ``FailureClassifier`` (pure, no LLM/network).
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import json
import logging
import os
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import yaml

from agentprobe.classifier.classifier import FailureClassifier
from agentprobe.classifier.taxonomy import FailureType
from agentprobe.models import AgentSpan, ToolCall
from agentprobe.regression.baseline import DEFAULT_BASELINE_NAME, load_baseline
from agentprobe.regression.stats import bootstrap_ci, mcnemar_test
from agentprobe.storage.db import init_db

logger = logging.getLogger("agentprobe")

# USD per 1,000 tokens, blended input+output (representative list pricing).
# An unknown model contributes 0.0 cost and emits a stderr warning.
COST_PER_1K_TOKENS: dict[str, float] = {
    "gpt-4o": 0.0025,
    "gpt-4o-mini": 0.00015,
    "gpt-4-turbo": 0.01,
    "gpt-4": 0.03,
    "gpt-3.5-turbo": 0.0005,
    "claude-3-5-sonnet": 0.003,
    "claude-3-haiku": 0.00025,
    "claude-3-opus": 0.015,
    "claude-opus-4": 0.015,
    "claude-sonnet-4": 0.003,
    "claude-haiku-4": 0.0008,
}

DEFAULT_REPORT_PATH = "agentprobe_report.json"

# Default accuracy-drop threshold when the suite omits one.
_DEFAULT_ACCURACY_DROP_MAX = 0.05

# The classifier is stateless; one shared instance suffices.
_CLASSIFIER = FailureClassifier()


@dataclass
class Case:
    """One parsed YAML test case."""

    id: str
    input: Any
    expected_contains: list[str] = field(default_factory=list)
    expected_tool_calls: Optional[list[str]] = None
    difficulty: str = "medium"


@dataclass
class RegressionResult:
    """The outcome of running a regression suite, with statistical context.

    ``accuracy_ci`` is a 95% bootstrap CI on ``accuracy``. ``baseline_accuracy``,
    ``accuracy_delta``, and ``cost_delta_pct`` are ``None`` when no baseline
    exists. ``accuracy_delta_significant`` is the McNemar significance (p < 0.05)
    of the paired per-case change versus the baseline; it is ``False`` when there
    is no baseline. ``failure_breakdown`` maps ``FailureType.value`` → count over
    the failed cases.
    """

    suite_name: str
    passed: bool
    n_cases: int
    n_passed: int
    accuracy: float
    accuracy_ci: tuple[float, float]
    baseline_accuracy: Optional[float]
    accuracy_delta: Optional[float]
    accuracy_delta_significant: bool
    avg_cost_usd: float
    cost_delta_pct: Optional[float]
    failure_breakdown: dict[str, int]
    generated_at: datetime

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict (for the uploaded eval report)."""
        return {
            "suite_name": self.suite_name,
            "passed": self.passed,
            "n_cases": self.n_cases,
            "n_passed": self.n_passed,
            "accuracy": self.accuracy,
            "accuracy_ci": list(self.accuracy_ci),
            "baseline_accuracy": self.baseline_accuracy,
            "accuracy_delta": self.accuracy_delta,
            "accuracy_delta_significant": self.accuracy_delta_significant,
            "avg_cost_usd": self.avg_cost_usd,
            "cost_delta_pct": self.cost_delta_pct,
            "failure_breakdown": self.failure_breakdown,
            "generated_at": self.generated_at.isoformat(),
        }


def _load_suite(suite_path: str) -> dict:
    """Parse the YAML suite file into a dict."""
    with open(suite_path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _parse_cases(raw_cases: list[dict]) -> list[Case]:
    """Convert raw YAML case dicts into :class:`Case` objects."""
    return [
        Case(
            id=rc["id"],
            input=rc["input"],
            expected_contains=rc.get("expected_contains", []) or [],
            expected_tool_calls=rc.get("expected_tool_calls"),
            difficulty=rc.get("difficulty", "medium"),
        )
        for rc in raw_cases
    ]


def _resolve_agent(suite_path: str, module_name: str, func_name: str) -> Callable:
    """Dynamically import ``module_name`` and return its ``func_name`` callable.

    The directory containing the suite file and the current working directory are
    prepended to ``sys.path`` so a project-local agent module imports cleanly.
    """
    for candidate in (os.path.dirname(os.path.abspath(suite_path)), os.getcwd()):
        if candidate and candidate not in sys.path:
            sys.path.insert(0, candidate)
    module = importlib.import_module(module_name)
    return getattr(module, func_name)


def _accepts_collector(func: Callable) -> bool:
    """Return whether ``func`` declares the opt-in ``_probe_collector`` param."""
    try:
        return "_probe_collector" in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


def _extract_tokens(output: Any) -> Optional[int]:
    """Extract a token count from a dict ``output`` carrying ``usage``."""
    if isinstance(output, dict) and "usage" in output:
        usage = output["usage"]
        if isinstance(usage, int):
            return usage
        if isinstance(usage, dict) and isinstance(usage.get("total_tokens"), int):
            return usage["total_tokens"]
    return None


def _extract_model(output: Any) -> Optional[str]:
    """Extract a model name from a dict ``output`` carrying ``model``."""
    if isinstance(output, dict) and isinstance(output.get("model"), str):
        return output["model"]
    return None


def _case_cost_usd(output: Any) -> float:
    """Estimate the USD cost of a case from its output's tokens and model.

    Returns ``0.0`` when tokens or model are absent (e.g. a plain-string agent).
    An unrecognised model is charged ``0.0`` with a stderr warning.
    """
    tokens = _extract_tokens(output)
    model = _extract_model(output)
    if not tokens or not model:
        return 0.0
    rate = COST_PER_1K_TOKENS.get(model)
    if rate is None:
        logger.warning("No cost entry for model %r; charging $0.00", model)
        return 0.0
    return (tokens / 1000.0) * rate


async def _run_case(
    target: Callable,
    case: Case,
    accepts_collector: bool,
) -> tuple[Any, list[ToolCall], Optional[str]]:
    """Run a single case, returning ``(output, tool_calls, exception_str)``."""
    collector: list[ToolCall] = []
    try:
        if accepts_collector:
            output = await target(case.input, _probe_collector=collector)
        else:
            output = await target(case.input)
        return output, collector, None
    except Exception:  # noqa: BLE001 — a raising case is a failed case, not a crash.
        return None, collector, traceback.format_exc()


def _score_case(case: Case, output: Any, tool_calls: list[ToolCall], failed: bool) -> bool:
    """Return whether the case passed: no exception, and all expectations met."""
    if failed:
        return False
    text = output if isinstance(output, str) else str(output)
    if any(needle not in text for needle in case.expected_contains):
        return False
    if case.expected_tool_calls:
        called = {tc.tool_name for tc in tool_calls}
        if any(tool not in called for tool in case.expected_tool_calls):
            return False
    return True


def _classify_failure(
    case: Case,
    output: Any,
    tool_calls: list[ToolCall],
    exception_str: Optional[str],
) -> str:
    """Label a failed case with a ``FailureType.value`` via the rule classifier."""
    span = AgentSpan(
        run_id="",
        agent_name=case.id,
        input=case.input,
        output=output,
        duration_ms=0.0,
        tool_calls=tool_calls,
        success=False,
        exception=exception_str,
    )
    failure_type, _ = _CLASSIFIER.classify(span)
    return (failure_type or FailureType.TASK_FAILED).value


@dataclass
class _Evaluation:
    """Raw per-case evaluation output, shared by run + baseline-snapshot paths."""

    outcomes: list[bool]
    case_results: dict[str, bool]
    costs: list[float]
    failure_breakdown: dict[str, int]


async def _evaluate(target: Callable, cases: list[Case], accepts_collector: bool) -> _Evaluation:
    """Run every case against ``target`` and collect raw pass/fail outcomes."""
    case_results: dict[str, bool] = {}
    outcomes: list[bool] = []
    costs: list[float] = []
    failure_breakdown: dict[str, int] = {}

    for case in cases:
        output, tool_calls, exception_str = await _run_case(target, case, accepts_collector)
        passed = _score_case(case, output, tool_calls, failed=exception_str is not None)
        case_results[case.id] = passed
        outcomes.append(passed)
        costs.append(_case_cost_usd(output))
        if not passed:
            label = _classify_failure(case, output, tool_calls, exception_str)
            failure_breakdown[label] = failure_breakdown.get(label, 0) + 1

    return _Evaluation(outcomes, case_results, costs, failure_breakdown)


def _prepare_suite(suite_path: str) -> tuple[dict, list[Case], Callable, bool]:
    """Load the suite and resolve its (undecorated) agent function."""
    suite = _load_suite(suite_path)
    cases = _parse_cases(suite.get("cases", []))
    agent = _resolve_agent(suite_path, suite["agent_module"], suite["agent_function"])
    # Evaluate the undecorated function so our injected collector is honoured.
    target = getattr(agent, "__wrapped__", agent)
    return suite, cases, target, _accepts_collector(target)


async def snapshot_baseline(
    suite_path: str,
    name: str = DEFAULT_BASELINE_NAME,
):
    """Run a suite and persist its metrics (with per-case results) as a baseline.

    This is the engine behind the future ``probe baseline save`` command
    (TASK 15). The persisted metrics include the per-case pass/fail vector so a
    later run can run a *paired* McNemar test against this baseline.

    Args:
        suite_path: Path to the YAML suite file.
        name: Baseline name to save under (default ``"main"``).

    Returns:
        The persisted :class:`~agentprobe.storage.models.RegressionBaseline` row.
    """
    from agentprobe.regression.baseline import save_baseline

    await init_db()
    _, cases, target, accepts_collector = _prepare_suite(suite_path)
    ev = await _evaluate(target, cases, accepts_collector)
    n_cases = len(cases)
    n_passed = sum(ev.outcomes)
    metrics = {
        "accuracy": (n_passed / n_cases) if n_cases else 0.0,
        "n_passed": n_passed,
        "n_cases": n_cases,
        "avg_cost_usd": (sum(ev.costs) / len(ev.costs)) if ev.costs else 0.0,
        "failure_breakdown": ev.failure_breakdown,
        "case_results": ev.case_results,
    }
    return await save_baseline(name, metrics, n_runs=n_cases)


async def run_suite(
    suite_path: str,
    fail_on_regression: bool = False,
    baseline_name: str = DEFAULT_BASELINE_NAME,
) -> RegressionResult:
    """Run a regression suite and compare it to its baseline.

    Loads the YAML suite, imports the agent, runs every case, and computes
    accuracy with a bootstrap CI. If a baseline named ``baseline_name`` exists,
    computes the accuracy delta and tests it for significance with McNemar's test
    on the paired per-case outcomes.

    A regression is *confirmed* only when the drop exceeds the suite's
    ``accuracy_drop_max`` **and** the change is significant. When
    ``fail_on_regression`` is set, a confirmed regression makes ``passed`` False
    (the caller should exit 1). A drop over threshold that is not significant
    logs a stderr warning and leaves ``passed`` True (the caller exits 0).

    Args:
        suite_path: Path to the YAML suite file.
        fail_on_regression: Whether a confirmed regression should fail the run.
        baseline_name: Baseline to compare against (default ``"main"``).

    Returns:
        The populated :class:`RegressionResult`.
    """
    await init_db()
    suite, cases, target, accepts_collector = _prepare_suite(suite_path)
    suite_name = suite.get("suite_name", "unnamed-suite")
    threshold = float(
        suite.get("thresholds", {}).get("accuracy_drop_max", _DEFAULT_ACCURACY_DROP_MAX)
    )

    ev = await _evaluate(target, cases, accepts_collector)
    case_results = ev.case_results
    outcomes = ev.outcomes
    failure_breakdown = ev.failure_breakdown

    n_cases = len(cases)
    n_passed = sum(outcomes)
    accuracy = (n_passed / n_cases) if n_cases else 0.0
    accuracy_ci = bootstrap_ci(outcomes) if outcomes else (0.0, 0.0)
    avg_cost_usd = (sum(ev.costs) / len(ev.costs)) if ev.costs else 0.0

    baseline_accuracy: Optional[float] = None
    accuracy_delta: Optional[float] = None
    delta_significant = False
    cost_delta_pct: Optional[float] = None

    baseline = await load_baseline(baseline_name)
    if baseline is not None:
        metrics = json.loads(baseline.metrics)
        baseline_accuracy = metrics.get("accuracy")
        if baseline_accuracy is not None:
            accuracy_delta = accuracy - baseline_accuracy

        baseline_results: dict[str, bool] = metrics.get("case_results", {})
        shared_ids = [cid for cid in case_results if cid in baseline_results]
        if shared_ids:
            before = [bool(baseline_results[cid]) for cid in shared_ids]
            after = [bool(case_results[cid]) for cid in shared_ids]
            _, delta_significant = mcnemar_test(before, after)

        baseline_cost = metrics.get("avg_cost_usd")
        if baseline_cost:
            cost_delta_pct = (avg_cost_usd - baseline_cost) / baseline_cost

    regression_confirmed = (
        accuracy_delta is not None
        and accuracy_delta < -threshold
        and delta_significant
    )
    if accuracy_delta is not None and accuracy_delta < -threshold and not delta_significant:
        print(
            f"WARNING: accuracy dropped {accuracy_delta:+.1%} (> {threshold:.0%} "
            f"threshold) but the change is NOT statistically significant "
            f"(McNemar p >= 0.05); not failing the build.",
            file=sys.stderr,
        )

    passed = not (fail_on_regression and regression_confirmed)

    return RegressionResult(
        suite_name=suite_name,
        passed=passed,
        n_cases=n_cases,
        n_passed=n_passed,
        accuracy=accuracy,
        accuracy_ci=accuracy_ci,
        baseline_accuracy=baseline_accuracy,
        accuracy_delta=accuracy_delta,
        accuracy_delta_significant=delta_significant,
        avg_cost_usd=avg_cost_usd,
        cost_delta_pct=cost_delta_pct,
        failure_breakdown=failure_breakdown,
        generated_at=datetime.now(timezone.utc),
    )


def write_report(result: RegressionResult, path: str = DEFAULT_REPORT_PATH) -> None:
    """Write the result as JSON to ``path`` (uploaded as a CI artifact)."""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(result.to_dict(), handle, indent=2)


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the ``python -m agentprobe.regression.runner`` argument parser.

    A convenience entry point only — the user-facing ``probe run`` CLI is
    TASK 15.
    """
    parser = argparse.ArgumentParser(description="Run an AgentProbe regression suite.")
    parser.add_argument("--suite", required=True, help="Path to the YAML suite file.")
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit 1 on a confirmed (significant) regression.",
    )
    parser.add_argument(
        "--baseline-name",
        default=DEFAULT_BASELINE_NAME,
        help='Baseline to compare against (default "main").',
    )
    parser.add_argument(
        "--report-path",
        default=DEFAULT_REPORT_PATH,
        help="Where to write the JSON report.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point: run a suite, write the report, return the exit code."""
    args = _build_arg_parser().parse_args(argv)
    result = asyncio.run(
        run_suite(
            args.suite,
            fail_on_regression=args.fail_on_regression,
            baseline_name=args.baseline_name,
        )
    )
    write_report(result, args.report_path)
    print(
        f"{result.suite_name}: {result.n_passed}/{result.n_cases} passed "
        f"(accuracy {result.accuracy:.1%}, CI "
        f"[{result.accuracy_ci[0]:.2f}, {result.accuracy_ci[1]:.2f}])"
    )
    return 0 if result.passed else 1


if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    raise SystemExit(main())
