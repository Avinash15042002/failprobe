<div align="center">

# 🛰️ AgentProbe

### Tells you **why** your LLM agent failed — not just *that* it did.

*A rule-based failure classifier, a meta-evaluator that scores your evaluator, and a statistically honest regression CI — in one library.*

[![CI](https://github.com/Avinash15042002/AgentProbe/actions/workflows/eval.yml/badge.svg)](https://github.com/Avinash15042002/AgentProbe/actions/workflows/eval.yml)
[![PyPI](https://img.shields.io/pypi/v/failprobe)](https://pypi.org/project/failprobe/)
[![Python](https://img.shields.io/pypi/pyversions/failprobe)](https://pypi.org/project/failprobe/)
[![License: MIT](https://img.shields.io/github/license/Avinash15042002/AgentProbe)](LICENSE)
[![Code style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
![Tests](https://img.shields.io/badge/tests-139%20passing-brightgreen)
![Type checked](https://img.shields.io/badge/types-pydantic%20v2-ff69b4)

</div>

---

## ✨ Why AgentProbe?

> LangFuse and LangSmith log **what** happened. AgentProbe classifies **why** it happened — and tells you whether your evaluator can even be trusted.

|  | Observability tools | **AgentProbe** |
|---|:---:|:---:|
| Logs runs & traces | ✅ | ✅ |
| **Classifies *why* a run failed** (14 types, no LLM) | ❌ | ✅ |
| **Scores your LLM judge** against human ground truth | ❌ | ✅ |
| **Fails PRs** on *statistically significant* regressions | ❌ | ✅ |
| Confidence intervals on every metric | ❌ | ✅ |
| Framework lock-in | varies | **none** |

---

## 📦 Install

```bash
pip install failprobe
```

> The distribution is **`failprobe`** on PyPI, but you still import it as `agentprobe`:
> `from agentprobe import probe`.

PostgreSQL and dashboard extras are optional:

```bash
pip install "failprobe[postgres]"    # asyncpg driver for Postgres
pip install "failprobe[dashboard]"   # Streamlit dashboard
```

---

## 🚀 How it works in 3 lines

```python
from agentprobe import probe

@probe(name="my-agent")
async def run_agent(query: str) -> str:
    return await your_existing_agent.arun(query)   # ← unchanged
```

That's it. AgentProbe captures the run, classifies any failure with **zero LLM calls**, persists it fire-and-forget (never blocking your agent), and surfaces it in the dashboard.

<details>
<summary><b>▶︎ Runnable end-to-end (copy-paste)</b></summary>

<br>

```python
import asyncio
from agentprobe import probe

@probe(name="demo-agent")
async def run_agent(query: str) -> str:
    return f"Handled: {query}"

print(asyncio.run(run_agent("what's the weather in Delhi?")))
# -> Handled: what's the weather in Delhi?
# The run is classified and persisted to ./agentprobe.db without blocking.
```

</details>

---

## 🧭 Architecture

```mermaid
flowchart LR
    A([Your agent]) -- "@probe" --> B[AgentSpan captured]
    B -. "fire-and-forget<br/>asyncio.create_task" .-> D[(SQLite / Postgres)]
    B --> C{{"FailureClassifier<br/>rule-based · no LLM · &lt;10ms"}}
    C --> D
    D --> E[FastAPI]
    E --> F[Next.js dashboard]
    D --> G["LLM Judge<br/>(semantic correctness)"]
    G --> H["Meta-Evaluation<br/>judge vs golden dataset"]
    D --> I["Regression engine<br/>bootstrap CI + McNemar"]
    I --> J["GitHub Actions<br/>fail PR on sig. regression"]

    classDef core fill:#1f6feb,stroke:#0b3d91,color:#fff;
    classDef store fill:#8957e5,stroke:#4b2a8a,color:#fff;
    classDef llm fill:#d29922,stroke:#9e6a00,color:#fff;
    class B,C core;
    class D store;
    class G,H llm;
```

---

## 🧠 The failure taxonomy

Every run is classified into a fixed taxonomy of **14 failure types** (plus an `unknown` fallback) — instantly, with no model call:

| 🔧 Tool-use | 🧩 Reasoning | 📤 Output | ⚙️ System |
|---|---|---|---|
| `wrong_tool` | `hallucinated_call` | `task_failed` | `exception` |
| `bad_params` | `context_overflow` | `partial_success` | `timeout` |
| `missing_tool` | `infinite_loop` | `refused` | `unknown` |
| `tool_timeout` | `wrong_format` | | |
| `tool_api_error` | | | |

The rule engine handles ≥90% of failures (string matching, fingerprinting, counters). The **LLM judge is reserved for semantic correctness only** — expensive calls where they actually add value.

---

## 📊 Statistical honesty, enforced

AgentProbe never reports a raw delta. A regression **fails your build only when the drop is both over threshold *and* statistically significant** (McNemar's exact test, p < 0.05):

```mermaid
flowchart TD
    S([Accuracy drop measured]) --> T{drop &gt; threshold?}
    T -- No --> P["✅ pass · exit 0"]
    T -- Yes --> U{McNemar p &lt; 0.05?}
    U -- No --> W["⚠️ warn only · exit 0"]
    U -- Yes --> F["❌ regression · exit 1 · Slack alert"]

    classDef ok fill:#238636,stroke:#0f5323,color:#fff;
    classDef warn fill:#d29922,stroke:#9e6a00,color:#fff;
    classDef bad fill:#da3633,stroke:#8b1a1a,color:#fff;
    class P ok;
    class W warn;
    class F bad;
```

Every accuracy number ships with a **bootstrap confidence interval**. Small samples are flagged: `n < 10` skips the CI; `n < 30` computes it but warns it may be unreliable.

---

## 🔁 Regression CI

Run the demo suite against your agent and gate PRs automatically:

```bash
# Run the 20-case demo suite (no baseline yet → exits 0)
python -m agentprobe.regression.runner --suite probe_tests.yml

# Snapshot the current metrics as the baseline
python -c "import asyncio; from agentprobe.regression.runner import snapshot_baseline; \
asyncio.run(snapshot_baseline('probe_tests.yml', 'main'))"

# Re-run with gating — exits 1 only on a *significant* regression
python -m agentprobe.regression.runner --suite probe_tests.yml --fail-on-regression
```

The bundled GitHub Actions workflow ([`.github/workflows/eval.yml`](.github/workflows/eval.yml)) runs this on every PR and uploads `agentprobe_report.json` as an artifact.

> 💡 The ergonomic `probe run` / `probe baseline save` CLI lands in TASK 15; the `python -m` commands above are the current equivalents.

---

## 🔬 Meta-Evaluation — the headline feature

AgentProbe's flagship capability answers *"how accurate is your LLM judge?"* by scoring it against a human-labelled **golden dataset** and reporting a bootstrapped confidence interval — so you can state the result honestly, e.g. **"my judge is 91% accurate ±4% on 100 labelled cases."**

<details>
<summary><b>📋 Building the initial golden dataset (manual milestone)</b></summary>

<br>

> **Status:** not yet run. Requires `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`) and human labelling — the steps below are reproducible; the accuracy number is a placeholder until the first real run.

1. Run your `@probe`-decorated demo agent enough times to collect ~50 spans.
2. For each run flagged into the review queue (judge confidence `< 0.6` or an ambiguous score in `[0.4, 0.6]`), open `/review` and label it pass/fail. Each label is appended to `agentprobe_golden.jsonl`.
   *(API equivalent: `POST /review/{run_id}` with `{"label": ..., "notes": ...}`.)*
3. Continue until the dataset reaches **50 manually labelled cases**.
4. Run the first meta-evaluation:

   ```bash
   probe meta-eval --golden agentprobe_golden.jsonl   # CLI (TASK 15)
   # or: GET /eval/judge-accuracy
   ```

5. Record the headline number here.

| Metric | Value |
|---|---|
| Judge accuracy | _TBD — pending first run_ |
| 95% CI | _TBD_ |
| Cases (n) | _TBD_ |

> Honesty rules (enforced in `meta_eval.py`): with `n < 10` the CI is skipped (`warning="too_few_cases"`); with `n < 30` it is computed but flagged (`warning="ci_may_be_unreliable"`).

</details>

---

## 🖥️ Dashboard

The Next.js dashboard gives you an **Overview** page (runs table, pass rate, and
failure-type breakdown) and a **run-detail** view that surfaces the classified
failure — e.g. an `INFINITE_LOOP` card with the repeated tool call that tripped
it. Launch the API and dashboard together with one command:

```bash
probe dashboard            # API on :8000, dashboard on http://localhost:3000
```

<!-- TODO: embed docs/dashboard-overview.png once a screenshot is captured. -->

---

## ⌨️ CLI reference

Installing the package exposes the `probe` command (6 commands, all rendered with `rich`):

| Command | What it does |
|---|---|
| `probe run --suite probe_tests.yml [--fail-on-regression]` | Run a YAML test suite, write a JSON report, and summarise pass/fail + regression. Exits `1` only on a confirmed (over-threshold **and** significant) regression. |
| `probe report --last 5 [--agent NAME] [--format table\|json]` | Summarise the most recent runs from the live API as a rich table. |
| `probe compare --baseline IDS --candidate IDS [--metric accuracy\|score\|cost]` | Compare two run sets on one metric, with CI bounds and a significance verdict. |
| `probe baseline save --name main [--suite ...]` | Run a suite and snapshot its metrics as a named regression baseline. |
| `probe baseline list` | List saved regression baselines (latest snapshot per name). |
| `probe meta-eval --golden agentprobe_golden.jsonl [--model ...]` | Score the LLM judge against a golden dataset and show accuracy ± CI. |
| `probe dashboard [--port 3000] [--api-port 8000]` | Start the FastAPI server and the Next.js dashboard together. |

Run `probe --help` (or `probe <command> --help`) for the full option list.

---

## ⚙️ Configuration

Zero configuration works out of the box. Override once via `configure(ProbeConfig(...))`
before using `@probe`, or per-field through environment variables.

| `ProbeConfig` field | Default | Env override | Description |
|---|---|---|---|
| `db_url` | `sqlite+aiosqlite:///agentprobe.db` | `AGENTPROBE_DB_URL` | SQLAlchemy async DB URL where spans are persisted. |
| `api_url` | `None` | `AGENTPROBE_API_URL` | If set, spans are POSTed to a remote API instead of stored locally. |
| `judge_model` | `claude-haiku-4` | `AGENTPROBE_JUDGE_MODEL` | Model identifier used by the LLM judge. |
| `judge_timeout` | `10.0` | — | Max seconds to wait for a single judge call. |
| `loop_threshold` | `3` | `AGENTPROBE_LOOP_THRESHOLD` | Repeated tool calls before `INFINITE_LOOP` fires. |
| `token_overflow_threshold` | `120000` | — | Token count above which `CONTEXT_OVERFLOW` is flagged. |
| `emit_console` | `True` | `AGENTPROBE_EMIT_CONSOLE` | Echo each span to the console. |
| `tags` | `{}` | — | Default tags merged into every recorded run. |

```python
from agentprobe import configure, ProbeConfig

configure(ProbeConfig(db_url="postgresql+asyncpg://probe:probe@localhost/agentprobe"))
```

> `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` are read from the environment and are
> required only when running the LLM judge. `AGENTPROBE_API_KEY` optionally
> protects the FastAPI server.

---

## 🛠️ Local setup

```bash
# 1. Clone & create a virtualenv (Python 3.11+)
git clone https://github.com/Avinash15042002/AgentProbe.git
cd AgentProbe
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1

# 2. Install (editable) with dev tooling
pip install -e ".[dev]"

# 3. Run the test suite
pytest -q                       # 118 passing

# 4. Start the API
uvicorn api.main:app --reload   # http://localhost:8000/docs
```

> 📦 Released on PyPI — `pip install failprobe` (see [Install](#-install)).

---

## 🗺️ Project status

| Area | Module | Status |
|---|---|:---:|
| `@probe` decorator + async tracer | `agentprobe/` | ✅ |
| Rule-based failure classifier | `agentprobe/classifier/` | ✅ |
| Storage (SQLAlchemy + Alembic) | `agentprobe/storage/` | ✅ |
| LLM judge + meta-evaluation | `agentprobe/evaluator/` | ✅ |
| Regression CI (stats · baseline · runner · alert) | `agentprobe/regression/` | ✅ |
| FastAPI server | `api/` | ✅ |
| Next.js dashboard | `dashboard/` | 🚧 partial |
| Typer CLI (`probe …`) | `agentprobe/cli/` | ✅ |
| Docker + PyPI packaging | — | ✅ v0.1.0 |

---

## 🧱 Built with

`Python 3.11` · `Pydantic v2` · `SQLAlchemy 2.0 (async)` · `Alembic` · `FastAPI` · `scipy` + `numpy` · `Anthropic` + `OpenAI` SDKs · `Next.js 15` · `Tailwind` · `Typer` · `Ruff`

---

## 🤝 Contributing

Contributions are welcome! Please read **[CONTRIBUTING.md](CONTRIBUTING.md)** for
the dev setup, the layer-ownership rules, and the test/lint gates every change
must pass. See **[CHANGELOG.md](CHANGELOG.md)** for release history.

---

<div align="center">

**Build the engine first, the UI second.** · Made with statistical honesty.

📄 [MIT License](LICENSE)

</div>
