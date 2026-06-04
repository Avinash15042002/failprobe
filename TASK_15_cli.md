# Task 15 — CLI (`cli/main.py`)

**Phase:** Month 4
**Module:** `cli/main.py`

---

## Goal

Implement all six CLI commands using `typer` for argument parsing and `rich` for output. The CLI is the power-user interface — it wraps the same API and library functions used by the dashboard.

---

## Commands

### `probe run` — Run a registered test suite

```bash
probe run --suite probe_tests.yml [--fail-on-regression] [--baseline-name main]
```

- Loads the YAML test suite
- Runs the agent function on every test case
- Compares against the stored baseline if `--fail-on-regression` is set
- Outputs a `rich` table summarising pass/fail per case
- Writes `agentprobe_report.json` to the working directory
- Exits 0 / 1 per regression rules (Task 14)

### `probe report` — Summary of recent runs

```bash
probe report --agent my-agent --last 50
```

- Queries `GET /runs?agent_name=<agent>&limit=<n>`
- Renders a `rich` table: run ID prefix, status, failure type, duration, timestamp
- Footer line: `Total: N runs | Pass rate: 87% | Most common failure: INFINITE_LOOP`

### `probe compare` — Compare two run sets

```bash
probe compare --baseline run-id-1,run-id-2 --candidate run-id-3,run-id-4
```

- Calls `POST /compare`
- Renders a delta table with CI bounds
- Prints significance result

### `probe baseline save` — Snapshot current metrics

```bash
probe baseline save --name "v1.2-main"
```

- Calls `baseline.save_baseline(name, current_result)`
- Confirms with: `✓ Baseline "v1.2-main" saved (n=47 runs, accuracy=91.4%)`

### `probe meta-eval` — Run meta-evaluation

```bash
probe meta-eval --golden agentprobe_golden.jsonl
```

- Loads golden dataset
- Calls `run_meta_eval()`
- Renders a `rich` panel: accuracy ± CI, precision, recall, F1, disagreement rate

### `probe dashboard` — Start the dashboard

```bash
probe dashboard [--port 3000]
```

- Starts the Next.js dashboard (or Streamlit in Month 1)
- Also starts the FastAPI server if not already running
- Prints: `Dashboard running at http://localhost:3000`

---

## Output Standards

- **All output must use `rich`** — no `print()` calls in CLI code.
- Tables: use `rich.table.Table`
- Progress: use `rich.progress.Progress` for long-running evaluations
- Errors: use `rich.console.Console().print("[red]Error: ...[/red]")`
- Success: use `✓` prefix in green
- Failure: use `✗` prefix in red

---

## Implementation Skeleton

```python
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="AgentProbe CLI — failure classification and regression CI for LLM agents")
console = Console()

@app.command()
def run(
    suite: str = typer.Option(..., help="Path to probe_tests.yml"),
    fail_on_regression: bool = typer.Option(False),
    baseline_name: str = typer.Option("main"),
):
    ...

@app.command()
def report(
    agent: str = typer.Option(None),
    last: int = typer.Option(50),
):
    ...

# etc.

if __name__ == "__main__":
    app()
```

---

## `pyproject.toml` entry point

```toml
[project.scripts]
probe = "agentprobe.cli.main:app"
```

After `pip install -e .`, `probe` is available as a shell command.

---

## Acceptance Criteria

- [ ] `probe --help` lists all six commands with descriptions
- [ ] `probe report` renders a rich table from live API data
- [ ] `probe run --suite probe_tests.yml` runs end-to-end without error
- [ ] `probe meta-eval --golden agentprobe_golden.jsonl` outputs accuracy ± CI
- [ ] `probe dashboard` starts both the API and the dashboard
- [ ] Zero `print()` calls in `cli/main.py` — only `rich` output
