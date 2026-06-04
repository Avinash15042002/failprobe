<div align="center">

# 🛰️ FailProbe

### Tells you **why** your LLM agent failed — not just *that* it did.

*A rule-based failure classifier, a meta-evaluator that scores your evaluator, and a statistically honest regression CI — in one library.*

[![CI](https://github.com/Avinash15042002/failprobe/actions/workflows/eval.yml/badge.svg)](https://github.com/Avinash15042002/failprobe/actions/workflows/eval.yml)
[![PyPI](https://img.shields.io/pypi/v/failprobe)](https://pypi.org/project/failprobe/)
[![Python](https://img.shields.io/pypi/pyversions/failprobe)](https://pypi.org/project/failprobe/)
[![License: MIT](https://img.shields.io/github/license/Avinash15042002/failprobe)](LICENSE)
[![Code style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

</div>

---

## ✨ Why FailProbe?

> LangFuse and LangSmith log **what** happened. FailProbe classifies **why** it happened — and tells you whether your evaluator can even be trusted.

|  | Observability tools | **FailProbe** |
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

Optional extras:

```bash
pip install "failprobe[postgres]"    # asyncpg driver for PostgreSQL
pip install "failprobe[dashboard]"   # Streamlit dashboard
```

Requires Python 3.11+.

---

## 🚀 Quickstart

Add one decorator to your existing async agent — nothing else changes:

```python
from failprobe import probe

@probe(name="my-agent")
async def run_agent(query: str) -> str:
    return await your_existing_agent.arun(query)   # ← unchanged
```

FailProbe captures the run, classifies any failure with **zero LLM calls**, and persists it fire-and-forget — it never blocks or alters your agent's output or exceptions.

<details>
<summary><b>▶︎ Runnable end-to-end (copy-paste)</b></summary>

<br>

```python
import asyncio
from failprobe import probe

@probe(name="demo-agent")
async def run_agent(query: str) -> str:
    return f"Handled: {query}"

print(asyncio.run(run_agent("what's the weather in Delhi?")))
# -> Handled: what's the weather in Delhi?
# The run is classified and persisted to ./failprobe.db without blocking.
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

The rule engine handles the vast majority of failures with string matching, fingerprinting, and counters. The **LLM judge is reserved for semantic correctness only** — the expensive calls where they actually add value.

---

## 📊 Statistical honesty, enforced

FailProbe never reports a raw delta. A regression **fails your build only when the drop is both over threshold *and* statistically significant** (McNemar's exact test, p < 0.05):

```mermaid
flowchart TD
    S([Accuracy drop measured]) --> T{drop &gt; threshold?}
    T -- No --> P["✅ pass · exit 0"]
    T -- Yes --> U{McNemar p &lt; 0.05?}
    U -- No --> W["⚠️ warn only · exit 0"]
    U -- Yes --> F["❌ regression · exit 1 · alert"]

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

Run a suite against your agent and gate pull requests automatically:

```bash
# Run the demo suite (no baseline yet → exits 0)
probe run --suite probe_tests.yml

# Snapshot the current metrics as the baseline
probe baseline save --name main --suite probe_tests.yml

# Re-run with gating — exits 1 only on a *significant* regression
probe run --suite probe_tests.yml --fail-on-regression
```

The bundled GitHub Actions workflow ([`.github/workflows/eval.yml`](.github/workflows/eval.yml)) runs this on every pull request and uploads `failprobe_report.json` as an artifact.

---

## 🔬 Meta-evaluation

FailProbe's flagship capability answers *"how accurate is your LLM judge?"* It scores the judge against a human-labelled **golden dataset** and reports a bootstrapped confidence interval, so you can state the result honestly — e.g. *"the judge is 91% accurate ±4% on 100 labelled cases."*

```bash
probe meta-eval --golden failprobe_golden.jsonl
```

The same honesty rules apply: with `n < 10` the confidence interval is skipped; with `n < 30` it is computed but flagged as potentially unreliable.

---

## 🖥️ Dashboard

The Next.js dashboard provides an **Overview** page (runs table, pass rate, and failure-type breakdown) and a **run-detail** view that surfaces the classified failure — for example, an `infinite_loop` card showing the repeated tool call that triggered it. Launch the API and dashboard together:

```bash
probe dashboard            # API on :8000, dashboard on http://localhost:3000
```

---

## ⌨️ CLI reference

Installing the package exposes the `probe` command (rendered with `rich`):

| Command | What it does |
|---|---|
| `probe run --suite probe_tests.yml [--fail-on-regression]` | Run a YAML test suite, write a JSON report, and summarise pass/fail + regression. Exits `1` only on a confirmed (over-threshold **and** significant) regression. |
| `probe report --last 5 [--agent NAME] [--format table\|json]` | Summarise the most recent runs from the live API as a table. |
| `probe compare --baseline IDS --candidate IDS [--metric accuracy\|score\|cost]` | Compare two run sets on one metric, with CI bounds and a significance verdict. |
| `probe baseline save --name main [--suite ...]` | Run a suite and snapshot its metrics as a named regression baseline. |
| `probe baseline list` | List saved regression baselines (latest snapshot per name). |
| `probe meta-eval --golden failprobe_golden.jsonl [--model ...]` | Score the LLM judge against a golden dataset and show accuracy ± CI. |
| `probe dashboard [--port 3000] [--api-port 8000]` | Start the FastAPI server and the Next.js dashboard together. |

Run `probe --help` (or `probe <command> --help`) for the full option list.

---

## ⚙️ Configuration

Zero configuration works out of the box. Override once via `configure(ProbeConfig(...))` before using `@probe`, or per-field through environment variables.

| `ProbeConfig` field | Default | Env override | Description |
|---|---|---|---|
| `db_url` | `sqlite+aiosqlite:///failprobe.db` | `FAILPROBE_DB_URL` | SQLAlchemy async DB URL where spans are persisted. |
| `api_url` | `None` | `FAILPROBE_API_URL` | If set, spans are POSTed to a remote API instead of stored locally. |
| `judge_model` | `claude-haiku-4` | `FAILPROBE_JUDGE_MODEL` | Model identifier used by the LLM judge. |
| `judge_timeout` | `10.0` | — | Max seconds to wait for a single judge call. |
| `loop_threshold` | `3` | `FAILPROBE_LOOP_THRESHOLD` | Repeated tool calls before `infinite_loop` fires. |
| `token_overflow_threshold` | `120000` | — | Token count above which `context_overflow` is flagged. |
| `emit_console` | `True` | `FAILPROBE_EMIT_CONSOLE` | Echo each span to the console. |
| `tags` | `{}` | — | Default tags merged into every recorded run. |

```python
from failprobe import configure, ProbeConfig

configure(ProbeConfig(db_url="postgresql+asyncpg://probe:probe@localhost/failprobe"))
```

> `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` are read from the environment and are required only when running the LLM judge. `FAILPROBE_API_KEY` optionally protects the FastAPI server.

---

## 🐳 Run the full stack with Docker

```bash
docker compose up --build        # API (:8000) + dashboard (:3000) + PostgreSQL
```

The default `docker-compose.yml` runs PostgreSQL; a lightweight SQLite stack is available via `docker compose -f docker-compose.dev.yml up`.

---

## 🛠️ Local development

```bash
# 1. Clone & create a virtualenv (Python 3.11+)
git clone https://github.com/Avinash15042002/failprobe.git
cd failprobe
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1

# 2. Install (editable) with dev tooling
pip install -e ".[dev]"

# 3. Run the test suite
pytest -q                       # the end-to-end test is excluded by default

# 4. Start the API
uvicorn api.main:app --reload   # http://localhost:8000/docs
```

---

## 🧱 Built with

`Python 3.11` · `Pydantic v2` · `SQLAlchemy 2.0 (async)` · `Alembic` · `FastAPI` · `scipy` + `numpy` · `Anthropic` + `OpenAI` SDKs · `Next.js 15` · `Tailwind` · `Typer` · `Ruff`

---

## 🤝 Contributing

Contributions are welcome. Please read **[CONTRIBUTING.md](CONTRIBUTING.md)** for the dev setup, the layer-ownership rules, and the test/lint gates every change must pass. See **[CHANGELOG.md](CHANGELOG.md)** for release history.

---

<div align="center">

Made with statistical honesty · 📄 [MIT License](LICENSE)

</div>
