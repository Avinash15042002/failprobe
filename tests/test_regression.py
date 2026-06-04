"""Tests for the regression layer (``agentprobe/regression/``).

Covers the statistical primitives (``bootstrap_ci``, ``mcnemar_test``,
``is_regression``) against the spec's acceptance criteria, plus two end-to-end
runner behaviours: an over-threshold-but-insignificant drop must NOT fail the
build (the most commonly broken case, Rule 10), and re-running a suite against
its own baseline must show no regression.

DB-backed tests use a fresh temporary SQLite file per test, mirroring
``test_storage.py``.
"""

from pathlib import Path

import numpy as np
import pytest
import yaml

from agentprobe.regression.baseline import load_baseline, save_baseline
from agentprobe.regression.runner import run_suite, snapshot_baseline
from agentprobe.regression.stats import bootstrap_ci, is_regression, mcnemar_test
from agentprobe.storage import db
from agentprobe.storage.db import init_db

PROBE_TESTS_YML = Path(__file__).resolve().parent.parent / "probe_tests.yml"


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch) -> None:
    """Point storage at a fresh temp SQLite file and reset engine singletons."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AGENTPROBE_DB_URL", f"sqlite+aiosqlite:///{db_file.as_posix()}")
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_session_factory", None)


# --------------------------------------------------------------------------- #
# stats.py — acceptance criteria
# --------------------------------------------------------------------------- #
def test_bootstrap_ci_on_accuracy_data() -> None:
    """``bootstrap_ci`` on 90% accuracy data yields a CI close to (0.83, 0.96)."""
    np.random.seed(0)
    lower, upper = bootstrap_ci([True] * 90 + [False] * 10)
    assert 0.80 <= lower <= 0.88
    assert 0.92 <= upper <= 0.99
    assert lower < upper


def test_mcnemar_identical_lists_not_significant() -> None:
    """Identical before/after vectors have no discordant pairs → not significant."""
    data = [True, False, True, True, False, True]
    p_value, significant = mcnemar_test(data, data)
    assert significant is False
    assert p_value == 1.0


def test_mcnemar_detects_a_clear_one_sided_change() -> None:
    """Many regressions and no improvements → a significant change."""
    before = [True] * 30
    after = [True] * 15 + [False] * 15  # 15 discordant pairs, all regressions
    p_value, significant = mcnemar_test(before, after)
    assert significant is True
    assert p_value < 0.05


def test_is_regression_true_when_ci_below_baseline() -> None:
    """A >5% drop whose current CI sits entirely below baseline is a regression."""
    assert is_regression(0.90, 0.84, (0.78, 0.89), threshold=0.05) is True


def test_is_regression_false_when_ci_crosses_baseline() -> None:
    """Same drop but the current CI still reaches the baseline → not a regression."""
    assert is_regression(0.90, 0.84, (0.80, 0.91), threshold=0.05) is False


# --------------------------------------------------------------------------- #
# runner.py — end-to-end behaviour
# --------------------------------------------------------------------------- #
def _write_suite(path: Path, cases: list[dict]) -> Path:
    """Write a minimal suite YAML targeting the demo weather/booking agent."""
    suite = {
        "suite_name": "unit-suite",
        "agent_module": "tests.demo_weather_agent",
        "agent_function": "run_agent",
        "thresholds": {"accuracy_drop_max": 0.05},
        "cases": cases,
    }
    path.write_text(yaml.safe_dump(suite), encoding="utf-8")
    return path


async def test_insignificant_drop_does_not_fail_build(tmp_path) -> None:
    """A large but statistically insignificant drop must NOT fail (exit-0 path).

    Baseline says all five cases passed. The current run fails two of them (a
    40% raw drop, well over the 5% threshold), but with only two discordant
    pairs McNemar's test is not significant (p = 0.5) — so the build must pass.
    """
    await init_db()
    cases = [
        {"id": "ok-1", "input": "weather in Delhi", "expected_contains": ["Delhi"]},
        {"id": "ok-2", "input": "weather in Tokyo", "expected_contains": ["Tokyo"]},
        {"id": "ok-3", "input": "book a hotel in London", "expected_contains": ["hotel"]},
        {"id": "fail-1", "input": "weather in Delhi", "expected_contains": ["NOPE_XYZ"]},
        {"id": "fail-2", "input": "weather in Tokyo", "expected_contains": ["NOPE_XYZ"]},
    ]
    suite_path = _write_suite(tmp_path / "suite.yml", cases)

    # Baseline: every case passed (accuracy 1.0).
    await save_baseline(
        "main",
        {"accuracy": 1.0, "case_results": {c["id"]: True for c in cases}},
        n_runs=len(cases),
    )

    result = await run_suite(str(suite_path), fail_on_regression=True)

    assert result.accuracy == pytest.approx(0.6)
    assert result.accuracy_delta is not None and result.accuracy_delta < -0.05
    assert result.accuracy_delta_significant is False
    assert result.passed is True  # over threshold but NOT significant → no fail


async def test_no_regression_against_own_baseline() -> None:
    """Re-running a suite against a baseline it just produced shows no regression."""
    await init_db()
    await snapshot_baseline(str(PROBE_TESTS_YML), name="main")
    assert await load_baseline("main") is not None

    result = await run_suite(str(PROBE_TESTS_YML), fail_on_regression=True)

    assert result.baseline_accuracy is not None
    assert result.accuracy_delta == pytest.approx(0.0)
    assert result.accuracy_delta_significant is False
    assert result.passed is True
    assert result.n_cases == 20
