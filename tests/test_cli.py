"""Tests for the AgentProbe CLI (``agentprobe/cli/main.py``).

Every command is exercised through Typer's :class:`CliRunner`. The CLI's seams —
the two HTTP helpers (``_api_get`` / ``_api_post``), the package functions it
wraps (``run_suite``, ``snapshot_baseline``, ``list_baselines``,
``run_meta_eval``), and the subprocess launcher (``_launch`` / ``_wait_for``) —
are monkeypatched, so no server, database, or child process is needed. We assert
on rendered ``stdout`` (rich output) and on exit codes (Rule 10).
"""

import json
from datetime import datetime, timezone

from typer.testing import CliRunner

from agentprobe.cli import main as cli_main
from agentprobe.cli.main import app
from agentprobe.evaluator.meta_eval import MetaEvalReport
from agentprobe.regression.runner import RegressionResult

runner = CliRunner()


def _make_result(*, passed: bool = True, n_cases: int = 20, with_baseline: bool = True) -> RegressionResult:
    """Build a fully-populated RegressionResult for render/exit-code assertions."""
    return RegressionResult(
        suite_name="demo-suite",
        passed=passed,
        n_cases=n_cases,
        n_passed=int(n_cases * 0.85),
        accuracy=0.85,
        accuracy_ci=(0.80, 0.90),
        baseline_accuracy=0.90 if with_baseline else None,
        accuracy_delta=-0.05 if with_baseline else None,
        accuracy_delta_significant=passed is False if with_baseline else False,
        avg_cost_usd=0.0012,
        cost_delta_pct=0.10 if with_baseline else None,
        failure_breakdown={"TASK_FAILED": 3},
        generated_at=datetime.now(timezone.utc),
    )


# --------------------------------------------------------------------------- #
# help / discovery
# --------------------------------------------------------------------------- #
def test_help_lists_all_six_commands() -> None:
    """``probe --help`` lists all six top-level commands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("run", "report", "compare", "baseline", "meta-eval", "dashboard"):
        assert command in result.output


# --------------------------------------------------------------------------- #
# probe run
# --------------------------------------------------------------------------- #
def test_run_passes_exit_zero(monkeypatch) -> None:
    """A passing suite renders a PASS summary and exits 0."""

    async def fake_run_suite(suite, fail_on_regression=False, baseline_name="main"):
        return _make_result(passed=True)

    monkeypatch.setattr(cli_main, "run_suite", fake_run_suite)
    monkeypatch.setattr(cli_main, "write_report", lambda result: None)

    result = runner.invoke(app, ["run", "--suite", "probe_tests.yml"])

    assert result.exit_code == 0
    assert "PASS" in result.output
    assert "Accuracy" in result.output
    assert "95% CI" in result.output  # statistical honesty: CI always shown


def test_run_confirmed_regression_exits_one(monkeypatch) -> None:
    """A confirmed regression with --fail-on-regression renders FAIL and exits 1."""

    async def fake_run_suite(suite, fail_on_regression=False, baseline_name="main"):
        return _make_result(passed=False)

    monkeypatch.setattr(cli_main, "run_suite", fake_run_suite)
    monkeypatch.setattr(cli_main, "write_report", lambda result: None)

    result = runner.invoke(app, ["run", "--suite", "probe_tests.yml", "--fail-on-regression"])

    assert result.exit_code == 1
    assert "FAIL" in result.output


def test_run_missing_suite_exits_two(monkeypatch) -> None:
    """A missing suite file is a clean error (exit 2), not a traceback."""

    async def fake_run_suite(suite, fail_on_regression=False, baseline_name="main"):
        raise FileNotFoundError(suite)

    monkeypatch.setattr(cli_main, "run_suite", fake_run_suite)

    result = runner.invoke(app, ["run", "--suite", "nope.yml"])

    assert result.exit_code == 2


# --------------------------------------------------------------------------- #
# probe report
# --------------------------------------------------------------------------- #
def test_report_renders_table_and_footer(monkeypatch) -> None:
    """``report`` renders a runs table with a pass-rate / common-failure footer."""

    def fake_get(path, params=None):
        assert path == "/runs"
        assert params["limit"] == 5
        return {
            "total": 2,
            "runs": [
                {
                    "id": "abcd1234ef",
                    "success": True,
                    "failure_type": None,
                    "duration_ms": 42.0,
                    "created_at": "2026-06-04T12:00:00+00:00",
                },
                {
                    "id": "ff00aa1199",
                    "success": False,
                    "failure_type": "INFINITE_LOOP",
                    "duration_ms": 99.0,
                    "created_at": "2026-06-04T12:01:00+00:00",
                },
            ],
        }

    monkeypatch.setattr(cli_main, "_api_get", fake_get)

    result = runner.invoke(app, ["report", "--last", "5"])

    assert result.exit_code == 0
    assert "Recent runs" in result.output
    assert "Pass rate:" in result.output
    assert "INFINITE_LOOP" in result.output


def test_report_json_format(monkeypatch) -> None:
    """``report --format json`` prints the raw API payload as JSON."""
    payload = {"total": 1, "runs": [{"id": "x", "success": True}]}
    monkeypatch.setattr(cli_main, "_api_get", lambda path, params=None: payload)

    result = runner.invoke(app, ["report", "--format", "json"])

    assert result.exit_code == 0
    assert '"runs"' in result.output


def test_report_passes_agent_filter(monkeypatch) -> None:
    """``--agent`` is forwarded to the API as the ``agent_name`` query param."""
    captured = {}

    def fake_get(path, params=None):
        captured.update(params or {})
        return {"total": 0, "runs": []}

    monkeypatch.setattr(cli_main, "_api_get", fake_get)

    result = runner.invoke(app, ["report", "--agent", "weather-agent"])

    assert result.exit_code == 0
    assert captured.get("agent_name") == "weather-agent"


# --------------------------------------------------------------------------- #
# probe compare
# --------------------------------------------------------------------------- #
def test_compare_renders_delta_and_significance(monkeypatch) -> None:
    """``compare`` splits ids, defaults metric to accuracy, and shows the verdict."""

    def fake_post(path, payload):
        assert path == "/compare"
        assert payload["metric"] == "accuracy"
        assert payload["baseline_run_ids"] == ["a", "b"]
        assert payload["candidate_run_ids"] == ["c", "d"]
        return {
            "metric": "accuracy",
            "n_baseline": 5,
            "n_candidate": 5,
            "baseline_mean": 0.90,
            "candidate_mean": 0.80,
            "delta": -0.10,
            "baseline_ci": [0.80, 0.97],
            "candidate_ci": [0.70, 0.90],
            "p_value": 0.03,
            "significant": True,
            "warning": "small_sample_ci_may_be_unreliable",
        }

    monkeypatch.setattr(cli_main, "_api_post", fake_post)

    result = runner.invoke(app, ["compare", "--baseline", "a, b", "--candidate", "c,d"])

    assert result.exit_code == 0
    assert "SIGNIFICANT" in result.output
    assert "Delta" in result.output
    assert "p = 0.0300" in result.output


# --------------------------------------------------------------------------- #
# probe baseline save / list
# --------------------------------------------------------------------------- #
def test_baseline_save_confirms(monkeypatch) -> None:
    """``baseline save`` snapshots a suite and confirms with n + accuracy."""

    class _Row:
        metrics = json.dumps({"accuracy": 0.85})
        n_runs = 20

    async def fake_snapshot(suite, name):
        assert name == "v1.2-main"
        return _Row()

    monkeypatch.setattr(cli_main, "snapshot_baseline", fake_snapshot)

    result = runner.invoke(app, ["baseline", "save", "--name", "v1.2-main"])

    assert result.exit_code == 0
    assert "v1.2-main" in result.output
    assert "n=20 runs" in result.output
    assert "85.0%" in result.output


def test_baseline_list_renders_rows(monkeypatch) -> None:
    """``baseline list`` renders one row per saved baseline."""

    class _Row:
        def __init__(self, name, accuracy, n_runs):
            self.name = name
            self.metrics = json.dumps({"accuracy": accuracy})
            self.n_runs = n_runs
            self.created_at = datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc)

    async def fake_list():
        return [_Row("main", 0.90, 20), _Row("release", 0.85, 18)]

    monkeypatch.setattr(cli_main, "list_baselines", fake_list)

    result = runner.invoke(app, ["baseline", "list"])

    assert result.exit_code == 0
    assert "Regression baselines" in result.output
    assert "main" in result.output
    assert "release" in result.output


def test_baseline_list_empty(monkeypatch) -> None:
    """``baseline list`` with no baselines prints a friendly notice, not a table."""

    async def fake_list():
        return []

    monkeypatch.setattr(cli_main, "list_baselines", fake_list)

    result = runner.invoke(app, ["baseline", "list"])

    assert result.exit_code == 0
    assert "No baselines" in result.output


# --------------------------------------------------------------------------- #
# probe meta-eval
# --------------------------------------------------------------------------- #
def test_meta_eval_renders_accuracy_and_ci(monkeypatch) -> None:
    """``meta-eval`` renders the judge's accuracy with its confidence interval."""

    class _FakeManager:
        def load(self, path):
            return ["case-1", "case-2"]  # non-empty; content irrelevant (judge faked)

    async def fake_meta(cases, judge_model):
        return MetaEvalReport(
            judge_accuracy=0.91,
            precision=0.90,
            recall=0.92,
            f1=0.91,
            confidence_interval=(0.87, 0.95),
            n_cases=100,
            n_correct=91,
            disagreement_rate=0.09,
            generated_at=datetime.now(timezone.utc),
            warning=None,
        )

    monkeypatch.setattr(cli_main, "GoldenDatasetManager", _FakeManager)
    monkeypatch.setattr(cli_main, "run_meta_eval", fake_meta)

    result = runner.invoke(app, ["meta-eval", "--golden", "golden.jsonl"])

    assert result.exit_code == 0
    assert "Meta-evaluation" in result.output
    assert "Accuracy" in result.output
    assert "95% CI" in result.output


def test_meta_eval_empty_dataset_exits_two(monkeypatch) -> None:
    """An empty golden dataset is a clean error (exit 2)."""

    class _FakeManager:
        def load(self, path):
            return []

    monkeypatch.setattr(cli_main, "GoldenDatasetManager", _FakeManager)

    result = runner.invoke(app, ["meta-eval", "--golden", "empty.jsonl"])

    assert result.exit_code == 2


# --------------------------------------------------------------------------- #
# probe dashboard
# --------------------------------------------------------------------------- #
def test_dashboard_launches_api_and_dashboard(monkeypatch) -> None:
    """``dashboard`` launches two processes and prints the dashboard URL."""
    launched: list[list[str]] = []

    def fake_launch(cmd):
        launched.append(cmd)
        return object()

    monkeypatch.setattr(cli_main, "_launch", fake_launch)
    monkeypatch.setattr(cli_main, "_wait_for", lambda procs: None)

    result = runner.invoke(app, ["dashboard", "--port", "3001"])

    assert result.exit_code == 0
    assert "Dashboard running at http://localhost:3001" in result.output
    assert len(launched) == 2
