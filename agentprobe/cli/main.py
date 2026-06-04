"""AgentProbe CLI — six commands wrapping the API and the package layers.

Layer ownership (see the project rules): the CLI never touches the database
directly. *Read* paths go through the REST API over HTTP (``report``,
``compare``); *compute/write* paths go through the library (``run``,
``baseline``, ``meta-eval``). Every line of output is rendered with ``rich`` —
there are zero ``print()`` calls in this module, so all human output is styled
and all error/warning text is routed through a :class:`~rich.console.Console`.

Statistical honesty (Rule 4) is preserved at the presentation layer: deltas are
always shown with their confidence interval and a significance verdict, and a
small-sample (n < 30) warning is surfaced where applicable.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from agentprobe.config import get_config
from agentprobe.evaluator.golden_dataset import DEFAULT_GOLDEN_PATH, GoldenDatasetManager
from agentprobe.evaluator.meta_eval import MetaEvalReport, run_meta_eval
from agentprobe.regression.baseline import DEFAULT_BASELINE_NAME, list_baselines
from agentprobe.regression.runner import (
    DEFAULT_REPORT_PATH,
    RegressionResult,
    run_suite,
    snapshot_baseline,
    write_report,
)

# On Windows the default console code page (e.g. cp1252) cannot encode the
# ✓/✗ status glyphs this CLI prints, which crashes rich mid-render. Switch
# stdout/stderr to UTF-8 where the streams support it (a no-op on already-UTF-8
# terminals and on captured test streams that lack ``reconfigure``).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):  # pragma: no cover - platform dependent
        pass

app = typer.Typer(
    help="AgentProbe CLI — failure classification and regression CI for LLM agents",
    no_args_is_help=True,
    add_completion=False,
)
baseline_app = typer.Typer(help="Save and list regression baselines.", no_args_is_help=True)
app.add_typer(baseline_app, name="baseline")

console = Console()
err_console = Console(stderr=True)

DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_SUITE_PATH = "probe_tests.yml"
DEFAULT_DASHBOARD_PORT = 3000
DEFAULT_API_PORT = 8000

# Below this many cases/runs a CI is statistically shaky — warn when shown.
_MIN_RELIABLE_N = 30

_NPM = "npm.cmd" if sys.platform == "win32" else "npm"


# --------------------------------------------------------------------------- #
# API + process seams (factored out so tests can monkeypatch them)
# --------------------------------------------------------------------------- #
def _api_base_url() -> str:
    """Return the API base URL (``AGENTPROBE_API_URL`` env, or the default)."""
    return os.environ.get("AGENTPROBE_API_URL", DEFAULT_API_URL).rstrip("/")


def _api_get(path: str, params: Optional[dict] = None) -> dict:
    """GET ``path`` from the AgentProbe API and return the decoded JSON body."""
    with httpx.Client(base_url=_api_base_url(), timeout=30.0) as client:
        response = client.get(path, params=params)
        response.raise_for_status()
        return response.json()


def _api_post(path: str, payload: dict) -> dict:
    """POST ``payload`` to ``path`` on the AgentProbe API; return the JSON body."""
    with httpx.Client(base_url=_api_base_url(), timeout=30.0) as client:
        response = client.post(path, json=payload)
        response.raise_for_status()
        return response.json()


def _launch(cmd: list[str]) -> subprocess.Popen:
    """Spawn ``cmd`` as a child process (a seam tests replace with a fake)."""
    return subprocess.Popen(cmd)  # noqa: S603 — args are CLI-controlled, not user input.


def _wait_for(procs: list[subprocess.Popen]) -> None:
    """Block until the launched processes exit, terminating them on Ctrl+C."""
    try:
        for proc in procs:
            proc.wait()
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        for proc in procs:
            proc.terminate()


def _split_ids(raw: str) -> list[str]:
    """Split a comma-separated run-id string into a clean list of ids."""
    return [piece.strip() for piece in raw.split(",") if piece.strip()]


def _http_error_message(exc: httpx.HTTPStatusError) -> str:
    """Extract the API's error envelope message from a failed HTTP response."""
    try:
        body = exc.response.json()
    except ValueError:
        return str(exc)
    return body.get("message") or body.get("error") or str(exc)


# --------------------------------------------------------------------------- #
# probe run
# --------------------------------------------------------------------------- #
@app.command()
def run(
    suite: str = typer.Option(..., "--suite", help="Path to the YAML test suite."),
    fail_on_regression: bool = typer.Option(
        False,
        "--fail-on-regression",
        help="Exit 1 on a confirmed (over-threshold AND significant) regression.",
    ),
    baseline_name: str = typer.Option(
        DEFAULT_BASELINE_NAME, "--baseline-name", help="Baseline to compare against."
    ),
) -> None:
    """Run a test suite, write a JSON report, and summarise pass/fail + regression."""
    try:
        result = asyncio.run(
            run_suite(
                suite,
                fail_on_regression=fail_on_regression,
                baseline_name=baseline_name,
            )
        )
    except FileNotFoundError:
        err_console.print(f"[red]Error: suite file not found: {suite}[/red]")
        raise typer.Exit(code=2)
    except Exception as exc:  # noqa: BLE001 — surface any failure as a clean CLI error.
        err_console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=2)

    write_report(result)
    _render_run_result(result)
    raise typer.Exit(code=0 if result.passed else 1)


def _render_run_result(result: RegressionResult) -> None:
    """Render a regression run as a summary table plus a failure breakdown."""
    table = Table(title=f"Suite: {result.suite_name}")
    table.add_column("Metric")
    table.add_column("Value", justify="right")

    status = "[green]✓ PASS[/green]" if result.passed else "[red]✗ FAIL[/red]"
    lower, upper = result.accuracy_ci
    table.add_row("Status", status)
    table.add_row("Cases passed", f"{result.n_passed}/{result.n_cases}")
    table.add_row("Accuracy", f"{result.accuracy:.1%}  (95% CI {lower:.1%}–{upper:.1%})")

    if result.baseline_accuracy is not None:
        table.add_row("Baseline accuracy", f"{result.baseline_accuracy:.1%}")
        delta = result.accuracy_delta or 0.0
        verdict = "significant" if result.accuracy_delta_significant else "not significant"
        colour = "red" if delta < 0 and result.accuracy_delta_significant else "yellow"
        table.add_row("Accuracy delta", f"[{colour}]{delta:+.1%}[/{colour}] ({verdict}, McNemar)")

    table.add_row("Avg cost / case", f"${result.avg_cost_usd:.4f}")
    if result.cost_delta_pct is not None:
        table.add_row("Cost delta", f"{result.cost_delta_pct:+.1%}")
    console.print(table)

    if result.failure_breakdown:
        breakdown = Table(title="Failure breakdown")
        breakdown.add_column("Failure type")
        breakdown.add_column("Count", justify="right")
        for failure_type, count in sorted(
            result.failure_breakdown.items(), key=lambda item: item[1], reverse=True
        ):
            breakdown.add_row(failure_type, str(count))
        console.print(breakdown)

    if result.n_cases < _MIN_RELIABLE_N:
        console.print(
            f"[yellow]⚠ n = {result.n_cases} (< {_MIN_RELIABLE_N}) — the confidence "
            "interval may be unreliable.[/yellow]"
        )
    console.print(f"[dim]Report written to {DEFAULT_REPORT_PATH}[/dim]")


# --------------------------------------------------------------------------- #
# probe report
# --------------------------------------------------------------------------- #
@app.command()
def report(
    agent: Optional[str] = typer.Option(None, "--agent", help="Filter by agent name."),
    last: int = typer.Option(50, "--last", help="Maximum number of recent runs to show."),
    output_format: str = typer.Option(
        "table", "--format", help="Output format: 'table' or 'json'."
    ),
) -> None:
    """Summarise the most recent agent runs from the live API."""
    params: dict = {"limit": last}
    if agent:
        params["agent_name"] = agent

    try:
        data = _api_get("/runs", params=params)
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error: {_http_error_message(exc)}[/red]")
        raise typer.Exit(code=2)
    except httpx.HTTPError as exc:
        err_console.print(
            f"[red]Error: could not reach API at {_api_base_url()}: {exc}[/red]"
        )
        raise typer.Exit(code=2)

    if output_format == "json":
        console.print_json(data=data)
        return

    _render_report_table(data.get("runs", []), total=data.get("total", 0))


def _render_report_table(runs: list[dict], total: int) -> None:
    """Render a runs table with a pass-rate / common-failure footer."""
    table = Table(title="Recent runs")
    table.add_column("Run")
    table.add_column("Status")
    table.add_column("Failure type")
    table.add_column("Duration (ms)", justify="right")
    table.add_column("Timestamp")

    n_passed = 0
    failure_counts: dict[str, int] = {}
    for entry in runs:
        success = bool(entry.get("success"))
        failure_type = entry.get("failure_type") or "—"
        if success:
            n_passed += 1
            status = "[green]✓[/green]"
        else:
            status = "[red]✗[/red]"
            if entry.get("failure_type"):
                failure_counts[failure_type] = failure_counts.get(failure_type, 0) + 1
        table.add_row(
            str(entry.get("id", ""))[:8],
            status,
            failure_type,
            f"{entry.get('duration_ms', 0.0):.0f}",
            str(entry.get("created_at", "")),
        )
    console.print(table)

    shown = len(runs)
    pass_rate = (n_passed / shown) if shown else 0.0
    most_common = max(failure_counts, key=failure_counts.get) if failure_counts else "none"
    console.print(
        f"[bold]Total:[/bold] {total} runs | "
        f"[bold]Pass rate:[/bold] {pass_rate:.0%} | "
        f"[bold]Most common failure:[/bold] {most_common}"
    )


# --------------------------------------------------------------------------- #
# probe compare
# --------------------------------------------------------------------------- #
@app.command()
def compare(
    baseline: str = typer.Option(..., "--baseline", help="Comma-separated baseline run IDs."),
    candidate: str = typer.Option(..., "--candidate", help="Comma-separated candidate run IDs."),
    metric: str = typer.Option(
        "accuracy", "--metric", help="Metric to compare: accuracy, score, or cost."
    ),
) -> None:
    """Compare two run sets on one metric, with CI bounds and a significance verdict."""
    payload = {
        "baseline_run_ids": _split_ids(baseline),
        "candidate_run_ids": _split_ids(candidate),
        "metric": metric,
    }
    try:
        data = _api_post("/compare", payload)
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error: {_http_error_message(exc)}[/red]")
        raise typer.Exit(code=2)
    except httpx.HTTPError as exc:
        err_console.print(
            f"[red]Error: could not reach API at {_api_base_url()}: {exc}[/red]"
        )
        raise typer.Exit(code=2)

    _render_compare(data)


def _render_compare(data: dict) -> None:
    """Render a baseline-vs-candidate delta table with CI bounds + significance."""
    table = Table(title=f"Comparison — metric: {data['metric']}")
    table.add_column("Group")
    table.add_column("N", justify="right")
    table.add_column("Mean", justify="right")
    table.add_column("95% CI", justify="right")

    baseline_ci = data["baseline_ci"]
    candidate_ci = data["candidate_ci"]
    table.add_row(
        "Baseline",
        str(data["n_baseline"]),
        f"{data['baseline_mean']:.3f}",
        f"[{baseline_ci[0]:.3f}, {baseline_ci[1]:.3f}]",
    )
    table.add_row(
        "Candidate",
        str(data["n_candidate"]),
        f"{data['candidate_mean']:.3f}",
        f"[{candidate_ci[0]:.3f}, {candidate_ci[1]:.3f}]",
    )
    console.print(table)

    p_value = data.get("p_value")
    p_str = f"p = {p_value:.4f}" if p_value is not None else "p = n/a (disjoint-CI test)"
    verdict = (
        "[red]SIGNIFICANT[/red]" if data["significant"] else "[green]not significant[/green]"
    )
    console.print(f"Delta: [bold]{data['delta']:+.3f}[/bold]  |  {p_str}  |  {verdict}")
    if data.get("warning"):
        console.print(f"[yellow]⚠ {data['warning']}[/yellow]")


# --------------------------------------------------------------------------- #
# probe baseline save / list
# --------------------------------------------------------------------------- #
@baseline_app.command("save")
def baseline_save(
    name: str = typer.Option(..., "--name", help="Name to save the baseline under."),
    suite: str = typer.Option(
        DEFAULT_SUITE_PATH, "--suite", help="Suite to run to compute the baseline metrics."
    ),
) -> None:
    """Run a suite and snapshot its metrics as a named regression baseline."""
    try:
        row = asyncio.run(snapshot_baseline(suite, name=name))
    except FileNotFoundError:
        err_console.print(f"[red]Error: suite file not found: {suite}[/red]")
        raise typer.Exit(code=2)
    except Exception as exc:  # noqa: BLE001 — surface any failure as a clean CLI error.
        err_console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=2)

    metrics = json.loads(row.metrics)
    accuracy = metrics.get("accuracy", 0.0)
    console.print(
        f'[green]✓[/green] Baseline "{name}" saved '
        f"(n={row.n_runs} runs, accuracy={accuracy:.1%})"
    )


@baseline_app.command("list")
def baseline_list() -> None:
    """List saved regression baselines (the latest snapshot per name)."""
    try:
        rows = asyncio.run(list_baselines())
    except Exception as exc:  # noqa: BLE001 — surface any failure as a clean CLI error.
        err_console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=2)

    if not rows:
        console.print("[yellow]No baselines saved yet.[/yellow]")
        return

    table = Table(title="Regression baselines")
    table.add_column("Name")
    table.add_column("Accuracy", justify="right")
    table.add_column("Runs", justify="right")
    table.add_column("Saved at")
    for row in rows:
        metrics = json.loads(row.metrics)
        accuracy = metrics.get("accuracy")
        accuracy_str = f"{accuracy:.1%}" if accuracy is not None else "—"
        table.add_row(row.name, accuracy_str, str(row.n_runs), row.created_at.isoformat())
    console.print(table)


# --------------------------------------------------------------------------- #
# probe meta-eval
# --------------------------------------------------------------------------- #
@app.command(name="meta-eval")
def meta_eval(
    golden: str = typer.Option(
        DEFAULT_GOLDEN_PATH, "--golden", help="Path to the golden JSONL dataset."
    ),
    model: Optional[str] = typer.Option(
        None, "--model", help="Judge model to evaluate (defaults to the configured model)."
    ),
) -> None:
    """Score the LLM judge against a golden dataset and show accuracy ± CI."""
    cases = GoldenDatasetManager().load(golden)
    if not cases:
        err_console.print(f"[red]Error: no golden cases found at {golden}[/red]")
        raise typer.Exit(code=2)

    judge_model = model or get_config().judge_model
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(f"Judging {len(cases)} golden cases…", total=None)
        report_data = asyncio.run(run_meta_eval(cases, judge_model=judge_model))

    _render_meta_eval(report_data, judge_model)


def _render_meta_eval(report_data: MetaEvalReport, model: str) -> None:
    """Render a meta-evaluation report as a rich panel (accuracy ± CI + metrics)."""
    lower, upper = report_data.confidence_interval
    half_width = (upper - lower) / 2
    lines = [
        f"Judge model:    {model}",
        f"Accuracy:       {report_data.judge_accuracy:.1%}  "
        f"(95% CI {lower:.1%}–{upper:.1%}, ±{half_width:.1%})",
        f"Precision:      {report_data.precision:.1%}",
        f"Recall:         {report_data.recall:.1%}",
        f"F1:             {report_data.f1:.1%}",
        f"Disagreement:   {report_data.disagreement_rate:.1%}",
        f"Cases:          {report_data.n_correct}/{report_data.n_cases} correct",
    ]
    console.print(Panel("\n".join(lines), title="Meta-evaluation", expand=False))

    if report_data.warning == "too_few_cases":
        console.print(
            "[yellow]⚠ Fewer than 10 cases — CI skipped; treat accuracy as "
            "indicative only.[/yellow]"
        )
    elif report_data.warning == "ci_may_be_unreliable":
        console.print(
            f"[yellow]⚠ n = {report_data.n_cases} (< {_MIN_RELIABLE_N}) — the "
            "confidence interval may be unreliable.[/yellow]"
        )


# --------------------------------------------------------------------------- #
# probe dashboard
# --------------------------------------------------------------------------- #
@app.command()
def dashboard(
    port: int = typer.Option(
        DEFAULT_DASHBOARD_PORT, "--port", help="Port to serve the dashboard on."
    ),
    api_port: int = typer.Option(
        DEFAULT_API_PORT, "--api-port", help="Port to serve the FastAPI API on."
    ),
) -> None:
    """Start the FastAPI server and the Next.js dashboard."""
    api_proc = _launch(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--port", str(api_port)]
    )
    console.print(f"[green]✓[/green] API running at http://localhost:{api_port}")

    dashboard_proc = _launch(
        [_NPM, "--prefix", "dashboard", "run", "dev", "--", "--port", str(port)]
    )
    console.print(f"[green]✓[/green] Dashboard running at http://localhost:{port}")
    console.print("[dim]Press Ctrl+C to stop both processes.[/dim]")

    _wait_for([api_proc, dashboard_proc])


if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    app()
