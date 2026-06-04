# AgentProbe — Complete Project Specification
> **For the coding agent:** This document is the single source of truth for building AgentProbe. Read it fully before writing any code. Every section is a contract — follow it exactly. When in doubt, ask before implementing.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Core Philosophy](#2-core-philosophy)
3. [Tech Stack](#3-tech-stack)
4. [Repository Structure](#4-repository-structure)
5. [Module Specifications](#5-module-specifications)
   - 5.1 [SDK — `agentprobe/`](#51-sdk--agentprobe)
   - 5.2 [Classifier — `agentprobe/classifier/`](#52-classifier--agentprobeclassifier)
   - 5.3 [Evaluator — `agentprobe/evaluator/`](#53-evaluator--agentprobeevaluator)
   - 5.4 [Storage — `agentprobe/storage/`](#54-storage--agentprobestorage)
   - 5.5 [Regression — `agentprobe/regression/`](#55-regression--agentproberegression)
   - 5.6 [API — `api/`](#56-api--api)
   - 5.7 [Dashboard — `dashboard/`](#57-dashboard--dashboard)
   - 5.8 [CLI — `cli/`](#58-cli--cli)
6. [Data Models](#6-data-models)
7. [Failure Taxonomy](#7-failure-taxonomy)
8. [API Contracts](#8-api-contracts)
9. [Build Phases](#9-build-phases)
10. [Testing Strategy](#10-testing-strategy)
11. [Configuration](#11-configuration)
12. [Packaging & Distribution](#12-packaging--distribution)
13. [CI/CD Pipeline](#13-cicd-pipeline)
14. [Environment Variables](#14-environment-variables)
15. [Coding Conventions](#15-coding-conventions)
16. [What NOT to Build](#16-what-not-to-build)

---

## 1. Project Overview

**AgentProbe** is an open-source Python library + dashboard that tells AI engineers *why* their LLM agent failed — not just that it did.

### The problem it solves

LangFuse and LangSmith log what happened. AgentProbe classifies *why* it happened and tells you whether your evaluator can even be trusted. Specifically:

- **Failure taxonomy**: every agent run is classified into one of 14 failure types automatically, with no LLM call needed for the first pass
- **Meta-evaluation**: the LLM judge that scores your agent is itself scored against a human-labelled golden dataset, so you can say "my evaluator is 91% accurate ±4%"
- **Regression CI**: a GitHub Actions workflow that fails a PR if accuracy drops >5% or cost increases >20%, using bootstrapped confidence intervals (not raw deltas)

### Who uses it

Any Python developer building agents with LangChain, LangGraph, CrewAI, or raw OpenAI/Anthropic API calls. Zero framework lock-in.

### How it works in 3 lines

```python
from agentprobe import probe

@probe(name="my-agent")
async def run_agent(query: str) -> str:
    return await your_existing_agent.arun(query)  # unchanged
```

That's it. AgentProbe captures the run, classifies any failure, saves to SQLite, and surfaces it in the dashboard.

---

## 2. Core Philosophy

> **Coding agent: internalize these before writing any code.**

1. **Zero config to start.** `pip install agentprobe` + one decorator = working. No API keys, no cloud signup, no config file needed for the basic case.

2. **Rule-based classifier first, LLM judge second.** The classifier must handle ≥90% of failures without an LLM call. LLM-as-judge is expensive and slow — use it only for semantic correctness, not structural failures.

3. **Never block the agent.** The `@probe` decorator must be non-blocking. Span emission is always fire-and-forget via `asyncio.create_task`. A failure in AgentProbe must never crash the user's agent.

4. **Depth over breadth.** A working failure classifier + meta-evaluation with real stats is worth more than a pretty dashboard with shallow metrics. Build the engine first, UI second.

5. **Statistically honest.** Never show a raw accuracy number without a confidence interval. Never show an A/B comparison without a significance test. If n < 30, show a warning.

6. **Self-hostable.** Everything runs locally with `docker compose up`. No mandatory external services.

---

## 3. Tech Stack

### Backend (Python package)

| Component | Choice | Reason |
|---|---|---|
| Language | Python 3.11+ | async/await, type hints, match statements |
| Async | `asyncio` | non-blocking span emission |
| Data models | `pydantic` v2 | fast validation, JSON serialization |
| ORM | `sqlalchemy` 2.0 async | works with SQLite (dev) and Postgres (prod) |
| Migrations | `alembic` | schema versioning |
| Stats | `scipy` + `numpy` | bootstrap CI, McNemar test |
| LLM calls | `anthropic` + `openai` SDKs | judge and meta-eval |
| Local inference | `ollama` Python client | zero-cost local evaluation |

### API

| Component | Choice |
|---|---|
| Framework | `FastAPI` with async routes |
| Server | `uvicorn` |
| Auth | API key via header (optional, off by default) |

### Dashboard

| Component | Choice |
|---|---|
| Framework | Next.js 15 (App Router) |
| UI components | Shadcn/UI + Tailwind CSS |
| Charts | Recharts |
| State | Zustand |
| API client | `fetch` with SWR for polling |

### CLI

| Component | Choice |
|---|---|
| Framework | `typer` |
| Output formatting | `rich` |

### Infrastructure

| Component | Choice |
|---|---|
| Database (dev) | SQLite via SQLAlchemy |
| Database (prod) | PostgreSQL 15 |
| Containerisation | Docker + Docker Compose |
| CI | GitHub Actions |

---

## 4. Repository Structure

```
agentprobe/                    ← root of the repo
│
├── agentprobe/                ← pip-installable Python package
│   ├── __init__.py            ← public API: exports probe, ProbeConfig, ProbeClient
│   ├── decorator.py           ← @probe decorator implementation
│   ├── tracer.py              ← async span collector, queue management
│   ├── config.py              ← ProbeConfig dataclass
│   │
│   ├── classifier/
│   │   ├── __init__.py
│   │   ├── classifier.py      ← main FailureClassifier class
│   │   ├── taxonomy.py        ← FailureType enum + descriptions
│   │   └── rules/
│   │       ├── __init__.py
│   │       ├── tool_errors.py ← wrong_tool, bad_params, missing_tool, timeouts
│   │       ├── loop_detector.py ← infinite loop detection via call fingerprinting
│   │       ├── hallucination.py ← hallucinated tool call detection
│   │       └── context.py     ← context overflow, token budget checks
│   │
│   ├── evaluator/
│   │   ├── __init__.py
│   │   ├── judge.py           ← LLM-as-judge: scores a run against rubric
│   │   ├── meta_eval.py       ← scores the judge against golden dataset
│   │   ├── golden_dataset.py  ← load/save/manage human-labelled cases
│   │   ├── confidence.py      ← judge disagreement detection, flag for review
│   │   └── prompts/
│   │       ├── judge_prompt.txt
│   │       └── rubric.txt
│   │
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── db.py              ← SQLAlchemy engine factory, session management
│   │   ├── models.py          ← ORM models: Run, Span, FailureEvent, EvalResult, GoldenCase
│   │   └── migrations/        ← Alembic migration files
│   │       ├── env.py
│   │       └── versions/
│   │
│   └── regression/
│       ├── __init__.py
│       ├── runner.py          ← loads test suite YAML, runs eval, compares baseline
│       ├── baseline.py        ← snapshot current metrics as baseline JSON
│       ├── stats.py           ← bootstrap CI, McNemar test, p-values
│       └── alert.py           ← Slack/email webhook on regression
│
├── api/
│   ├── main.py                ← FastAPI app, CORS, lifespan
│   ├── schemas.py             ← Pydantic response models for all routes
│   └── routes/
│       ├── __init__.py
│       ├── runs.py            ← GET /runs, GET /runs/{id}
│       ├── failures.py        ← GET /failures, GET /failures/taxonomy
│       ├── eval.py            ← POST /eval/run, GET /eval/judge-accuracy
│       ├── compare.py         ← POST /compare
│       └── golden.py          ← CRUD /golden
│
├── dashboard/
│   ├── package.json
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   └── app/
│       ├── layout.tsx
│       ├── page.tsx           ← overview: run history, failure rate
│       ├── runs/
│       │   └── [id]/page.tsx  ← single run: trace timeline, failure detail
│       ├── failures/
│       │   └── page.tsx       ← taxonomy heatmap, confusion matrix
│       ├── eval/
│       │   └── page.tsx       ← judge accuracy, golden dataset manager
│       ├── compare/
│       │   └── page.tsx       ← A/B comparison with CI bars
│       └── review/
│           └── page.tsx       ← human-in-loop review queue
│
├── cli/
│   └── main.py                ← typer CLI: probe run / probe report / probe compare
│
├── tests/
│   ├── conftest.py
│   ├── fixtures/              ← sample agent traces (JSON)
│   ├── test_classifier.py
│   ├── test_meta_eval.py
│   ├── test_regression.py
│   └── test_api.py
│
├── .github/
│   └── workflows/
│       └── eval.yml           ← regression CI on every PR
│
├── docker-compose.yml
├── Dockerfile.api
├── pyproject.toml
├── alembic.ini
└── README.md
```

---

## 5. Module Specifications

### 5.1 SDK — `agentprobe/`

#### `__init__.py` — Public API

```python
# Everything a user needs should be importable from the top-level package
from agentprobe import probe, ProbeConfig, ProbeClient
```

Export exactly these three names. Nothing else at the top level.

#### `config.py` — ProbeConfig

```python
@dataclass
class ProbeConfig:
    db_url: str = "sqlite+aiosqlite:///agentprobe.db"
    api_url: Optional[str] = None        # if set, spans are sent to remote API
    judge_model: str = "claude-haiku-4"  # cheap model for judge calls
    judge_timeout: float = 10.0          # seconds per judge call
    loop_threshold: int = 3              # repeated calls before INFINITE_LOOP fires
    token_overflow_threshold: int = 120_000
    emit_console: bool = True            # print classified spans to stdout
    tags: dict = field(default_factory=dict)  # default tags for all runs
```

**Rules:**
- `ProbeConfig` is a global singleton per process, initialized once
- Users set it before using `@probe`: `agentprobe.configure(ProbeConfig(...))`
- All defaults must work without any user configuration

#### `decorator.py` — @probe

The decorator must:

1. Wrap any `async` function (sync support is stretch goal, not in scope now)
2. Record: `run_id` (UUID4), `agent_name`, `input`, `output`, `duration_ms`, `tokens_used`, `model`, `success`, `exception`
3. Call `FailureClassifier.classify(span)` synchronously after the run
4. Call `asyncio.create_task(_emit_span(span))` — never `await` it directly
5. Never raise an exception of its own — if AgentProbe itself errors, log to stderr and return the agent's original output/exception unmodified

**Signature:**
```python
def probe(
    name: str,
    expected_output: Any = None,
    timeout: Optional[float] = None,
    model: Optional[str] = None,
    tags: Optional[dict] = None,
) -> Callable
```

**Tool call injection pattern:**
- If the wrapped function receives a kwarg `_probe_collector: list`, the decorator injects a fresh list before the call. The agent appends `ToolCall` objects to this list during execution.
- This is the opt-in pattern for agents that want per-tool-call tracking.

#### `tracer.py` — Async Emitter

```python
async def _emit_span(span: AgentSpan) -> None:
    # Phase 1 (month 1): write to SQLite via storage layer
    # Phase 2 (month 2): if api_url set, POST to /collector endpoint
    # Always: print to console if emit_console=True
```

- Must be wrapped in `try/except Exception` — never propagate errors
- Batch writes: collect spans in an in-memory queue, flush every 100ms or when queue hits 50 items

---

### 5.2 Classifier — `agentprobe/classifier/`

#### `taxonomy.py` — FailureType Enum

```python
class FailureType(Enum):
    # Tool-use failures
    WRONG_TOOL        = "wrong_tool"
    BAD_PARAMS        = "bad_params"
    MISSING_TOOL      = "missing_tool"
    TOOL_TIMEOUT      = "tool_timeout"
    TOOL_API_ERROR    = "tool_api_error"

    # Reasoning failures
    HALLUCINATED_CALL = "hallucinated_call"
    CONTEXT_OVERFLOW  = "context_overflow"
    INFINITE_LOOP     = "infinite_loop"
    WRONG_FORMAT      = "wrong_format"

    # Output failures
    TASK_FAILED       = "task_failed"
    PARTIAL_SUCCESS   = "partial_success"
    REFUSED           = "refused"

    # System failures
    EXCEPTION         = "exception"
    TIMEOUT           = "timeout"
    UNKNOWN           = "unknown"
```

Every `FailureType` must have a corresponding entry in `FAILURE_DESCRIPTIONS: dict[FailureType, str]`.

#### `classifier.py` — FailureClassifier

**Interface:**
```python
class FailureClassifier:
    def classify(self, span: AgentSpan) -> tuple[FailureType | None, str]:
        """
        Returns (FailureType, explanation) or (None, "success") if no failure.
        Must be synchronous. Must complete in <10ms for 99th percentile.
        Must not make any network or LLM calls.
        """
```

**Classification priority order** (check in this exact order, stop at first match):

1. `exception` field set → `EXCEPTION` or `TIMEOUT` based on exception type string
2. `asyncio.TimeoutError` in exception → `TIMEOUT`
3. Loop detection on `tool_calls` → `INFINITE_LOOP`
4. Any `ToolCall.error` set → route to `_classify_tool_error(tc)`
5. `tokens_used > config.token_overflow_threshold` → `CONTEXT_OVERFLOW`
6. Output text matches refusal pattern → `REFUSED`
7. `success=False` and `failure_msg` contains "partial" → `PARTIAL_SUCCESS`
8. `success=False` → `TASK_FAILED`
9. Fall through → `(None, "success")`

#### `rules/loop_detector.py`

**Algorithm:**
```
fingerprint = (tool_name, frozenset(params.items()))
If any fingerprint appears >= loop_threshold times → INFINITE_LOOP
Also check: if last N calls have identical tool_name regardless of params → INFINITE_LOOP
```

- `N` defaults to `config.loop_threshold` (default 3)
- If `params` contains unhashable values, fall back to `str(params)` for fingerprint

#### `rules/tool_errors.py`

Parse `ToolCall.error` string and map to failure type:

| Error pattern | FailureType |
|---|---|
| "timeout", "timed out" | `TOOL_TIMEOUT` |
| "not found", "no tool", "undefined", "does not exist" | `MISSING_TOOL` |
| "invalid", "missing", "required", "type error", "validation" | `BAD_PARAMS` |
| HTTP status codes 4xx/5xx in string | `TOOL_API_ERROR` |
| Anything else | `TOOL_API_ERROR` |

#### `rules/hallucination.py`

Detect hallucinated tool calls — agent claimed to call a tool that wasn't in the allowed toolset:

```python
def detect_hallucinated_calls(
    tool_calls: list[ToolCall],
    allowed_tools: list[str]   # passed from ProbeConfig or decorator kwarg
) -> tuple[bool, str]:
```

If `allowed_tools` is empty/None, skip this check (can't detect without a reference list).

---

### 5.3 Evaluator — `agentprobe/evaluator/`

> **Build this in month 2. Do not start until the classifier + storage are working.**

#### `judge.py` — LLM-as-Judge

**Interface:**
```python
@dataclass
class JudgeResult:
    run_id: str
    score: float          # 0.0 to 1.0
    reasoning: str        # judge's explanation
    model_used: str
    latency_ms: float
    confidence: float     # 0.0 to 1.0, judge's self-reported confidence

async def judge_run(
    span: AgentSpan,
    rubric: str,
    model: str = "claude-haiku-4",
) -> JudgeResult:
```

**Prompt structure** (`prompts/judge_prompt.txt`):
```
You are an expert AI evaluator. Evaluate the following agent run.

TASK INPUT: {input}
AGENT OUTPUT: {output}
TOOL CALLS MADE: {tool_calls_summary}

RUBRIC:
{rubric}

Respond in JSON with exactly these fields:
{
  "score": <float 0.0-1.0>,
  "reasoning": "<one paragraph>",
  "confidence": <float 0.0-1.0>,
  "key_issues": ["<issue1>", "<issue2>"]
}

Return ONLY the JSON. No preamble, no markdown.
```

**Rules:**
- Parse response as JSON. If parsing fails, retry once with a stricter prompt. If second attempt fails, return `JudgeResult(score=0.0, confidence=0.0, reasoning="parse_error")`
- Never let a judge error propagate — always return a JudgeResult
- Log all judge calls to storage as `EvalResult` rows

#### `meta_eval.py` — Meta-Evaluation

This is the most important feature. It answers: "how accurate is your judge?"

**Interface:**
```python
@dataclass
class MetaEvalReport:
    judge_accuracy: float        # % of golden cases correctly scored
    precision: float
    recall: float
    f1: float
    confidence_interval: tuple[float, float]  # 95% bootstrap CI
    n_cases: int
    n_correct: int
    disagreement_rate: float     # % where judge and human disagree
    generated_at: datetime

async def run_meta_eval(
    golden_dataset: list[GoldenCase],
    judge_model: str,
    threshold: float = 0.5,      # score >= threshold = "pass"
) -> MetaEvalReport:
```

**Algorithm:**
1. For each `GoldenCase` in the dataset, run `judge_run(case.span, rubric)`
2. Compare `JudgeResult.score >= threshold` against `GoldenCase.human_label` (pass/fail)
3. Compute precision, recall, F1
4. Compute 95% bootstrap CI on accuracy (1000 resamples)
5. Return `MetaEvalReport`

**Bootstrap CI implementation** (in `regression/stats.py`, reused here):
```python
def bootstrap_ci(data: list[bool], n_resamples: int = 1000, ci: float = 0.95) -> tuple[float, float]:
    means = [np.mean(np.random.choice(data, len(data), replace=True)) for _ in range(n_resamples)]
    alpha = (1 - ci) / 2
    return (np.quantile(means, alpha), np.quantile(means, 1 - alpha))
```

#### `golden_dataset.py` — Golden Dataset Manager

```python
@dataclass
class GoldenCase:
    id: str                       # UUID
    span: AgentSpan               # the agent run
    human_label: bool             # True = pass, False = fail
    human_notes: str              # reviewer's reasoning
    difficulty: str               # "easy" | "medium" | "hard" | "adversarial"
    created_at: datetime
    reviewed_by: str              # reviewer identifier

class GoldenDatasetManager:
    def load(self, path: str) -> list[GoldenCase]: ...
    def save(self, cases: list[GoldenCase], path: str) -> None: ...
    def add_case(self, case: GoldenCase) -> None: ...
    def get_stats(self) -> dict: ...  # n_cases, pass_rate, difficulty_distribution
```

- Golden dataset is stored as JSONL file (one case per line)
- Default path: `agentprobe_golden.jsonl` in working directory
- Cases flagged by `confidence.py` are added here after human review

---

### 5.4 Storage — `agentprobe/storage/`

#### `models.py` — ORM Models

```python
class Run(Base):
    __tablename__ = "runs"
    id: str                    # UUID, primary key
    agent_name: str
    input_text: str            # JSON-serialized input
    output_text: Optional[str] # JSON-serialized output
    duration_ms: float
    tokens_used: Optional[int]
    model: Optional[str]
    success: bool
    failure_type: Optional[str]  # FailureType.value
    failure_msg: Optional[str]
    exception: Optional[str]
    tags: str                  # JSON dict
    created_at: datetime

class ToolCallRecord(Base):
    __tablename__ = "tool_calls"
    id: str                    # UUID
    run_id: str                # FK → runs.id
    tool_name: str
    params: str                # JSON
    result: Optional[str]      # JSON
    duration_ms: float
    error: Optional[str]
    timestamp: datetime

class EvalResult(Base):
    __tablename__ = "eval_results"
    id: str
    run_id: str                # FK → runs.id
    judge_model: str
    score: float
    reasoning: str
    confidence: float
    human_label: Optional[bool]
    human_notes: Optional[str]
    created_at: datetime

class RegressionBaseline(Base):
    __tablename__ = "regression_baselines"
    id: str
    name: str                  # e.g. "main-branch-v1.2"
    metrics: str               # JSON: {accuracy, avg_score, failure_rate, avg_cost}
    n_runs: int
    created_at: datetime
```

#### `db.py` — Database Engine

```python
# Must support both SQLite (dev) and PostgreSQL (prod)
# Connection string from ProbeConfig.db_url
# Use async SQLAlchemy: AsyncSession, AsyncEngine
# Provide get_session() as async context manager

async def get_session() -> AsyncGenerator[AsyncSession, None]: ...
async def init_db() -> None: ...  # creates tables if not exist
```

---

### 5.5 Regression — `agentprobe/regression/`

> **Build this in month 3.**

#### `runner.py` — Regression Test Runner

Test suite format (YAML file, `probe_tests.yml`):
```yaml
# probe_tests.yml — place in project root
suite_name: "my-agent-eval"
agent_module: "myproject.agent"    # importable path to agent function
agent_function: "run_agent"

thresholds:
  accuracy_drop_max: 0.05          # fail if accuracy drops >5%
  cost_increase_max: 0.20          # fail if cost increases >20%
  latency_p90_max_ms: 5000         # fail if p90 latency exceeds 5s

cases:
  - id: "basic-weather"
    input: "What's the weather in Delhi?"
    expected_contains: ["Delhi", "temperature"]   # fuzzy match
    difficulty: "easy"

  - id: "multi-step-booking"
    input: "Book a flight from Delhi to Mumbai on June 15"
    expected_tool_calls: ["search_flights", "check_availability"]
    difficulty: "medium"
```

**Runner output:**
```python
@dataclass
class RegressionResult:
    suite_name: str
    passed: bool
    n_cases: int
    n_passed: int
    accuracy: float
    accuracy_ci: tuple[float, float]
    baseline_accuracy: Optional[float]
    accuracy_delta: Optional[float]
    accuracy_delta_significant: bool    # p < 0.05
    avg_cost_usd: float
    cost_delta_pct: Optional[float]
    failure_breakdown: dict[str, int]   # FailureType.value → count
    generated_at: datetime
```

#### `stats.py` — Statistical Tests

```python
def bootstrap_ci(
    data: list[bool | float],
    n_resamples: int = 1000,
    ci: float = 0.95
) -> tuple[float, float]: ...

def mcnemar_test(
    before: list[bool],
    after: list[bool]
) -> tuple[float, bool]:
    """Returns (p_value, is_significant). Significant if p < 0.05."""
    ...

def is_regression(
    baseline: float,
    current: float,
    ci: tuple[float, float],
    threshold: float = 0.05
) -> bool:
    """True if current - baseline < -threshold AND CI lower bound < 0."""
    ...
```

**Rule:** never display a regression alert unless the delta is both above the threshold AND statistically significant (p < 0.05). Raw deltas without significance testing are misleading and must not be shown.

---

### 5.6 API — `api/`

#### `main.py`

```python
app = FastAPI(title="AgentProbe API", version="0.1.0")

# CORS: allow localhost:3000 (dashboard) by default
# Lifespan: call storage.init_db() on startup
# Health check: GET /health → {"status": "ok", "version": "0.1.0"}
```

#### Route Specifications

**`GET /runs`**
```
Query params:
  agent_name: str (optional filter)
  success: bool (optional filter)
  failure_type: str (optional filter)
  limit: int = 50
  offset: int = 0
  order: "asc" | "desc" = "desc"

Response: {
  total: int,
  runs: Run[]
}
```

**`GET /runs/{run_id}`**
```
Response: {
  run: Run,
  tool_calls: ToolCallRecord[],
  eval_result: EvalResult | null
}
```

**`GET /failures/taxonomy`**
```
Response: {
  breakdown: { [FailureType]: { count: int, description: str, pct: float } },
  total_failures: int,
  total_runs: int,
  failure_rate: float
}
```

**`GET /failures`**
```
Query: agent_name, failure_type, from_date, to_date, limit, offset
Response: { total: int, failures: FailureEvent[] }
```

**`POST /eval/run`**
```
Body: { run_id: str, model?: str }
Response: EvalResult
```

**`GET /eval/judge-accuracy`**
```
Response: MetaEvalReport | { error: "no_golden_dataset" }
```

**`POST /compare`**
```
Body: {
  baseline_run_ids: str[],
  candidate_run_ids: str[],
  metric: "accuracy" | "score" | "cost"
}
Response: {
  baseline_mean: float,
  candidate_mean: float,
  delta: float,
  ci_lower: float,
  ci_upper: float,
  p_value: float,
  is_significant: bool,
  n_baseline: int,
  n_candidate: int
}
```

**`GET /golden`**, **`POST /golden`**, **`PATCH /golden/{id}`**, **`DELETE /golden/{id}`**
Standard CRUD for `GoldenCase` records.

**`GET /review/queue`**
```
Response: { cases: AgentSpan[] }  # spans flagged for human review
```

**`POST /review/{run_id}`**
```
Body: { label: bool, notes: str }
# Saves to golden dataset, removes from review queue
```

---

### 5.7 Dashboard — `dashboard/`

> **Build a working Streamlit version in month 1, then replace with Next.js in month 2.**

#### Pages

**`/` — Overview**
- Table of recent runs: columns = `agent_name`, `status (✓/✗)`, `failure_type`, `duration_ms`, `tokens`, `time`
- Failure rate sparkline (last 7 days)
- Top 3 failure types as pill badges with counts

**`/runs/[id]` — Run Detail**
- Header: agent name, input, output, duration, model, tags
- Trace timeline: horizontal waterfall chart of tool calls with duration bars
- Failure card: type badge, explanation text, raw exception if present
- Eval result: judge score bar, reasoning text, confidence indicator

**`/failures` — Failure Analytics**
- Taxonomy heatmap: FailureType on Y-axis, time buckets on X-axis, cell = count
- Confusion matrix: only shown if meta-eval has been run
- Failure type distribution: bar chart sorted by frequency

**`/eval` — Evaluation**
- Judge accuracy card: big number with ± CI range
- Golden dataset table: case ID, difficulty, human label, judge score, match/mismatch
- "Run meta-eval" button → `POST /eval/run` on all golden cases
- "Add to golden dataset" button on any run from the review queue

**`/compare` — A/B Comparison**
- Two multi-select dropdowns: baseline runs, candidate runs
- On compare: show delta table with CI bars (green if positive, red if negative)
- Significance indicator: "Statistically significant (p=0.02)" or "Not significant (p=0.34, n too small)"

**`/review` — Human Review Queue**
- Table of flagged runs (judge confidence < 0.6 or judge disagreement)
- Each row: input text, output text, judge score, pass/fail buttons, notes textarea

---

### 5.8 CLI — `cli/`

```bash
# Run a registered test suite
probe run --suite probe_tests.yml

# Show a summary report of recent runs
probe report --agent my-agent --last 50

# Compare two sets of runs
probe compare --baseline run-id-1,run-id-2 --candidate run-id-3,run-id-4

# Save current metrics as baseline
probe baseline save --name "v1.2-main"

# Run meta-evaluation
probe meta-eval --golden agentprobe_golden.jsonl

# Start the dashboard
probe dashboard
```

Output must use `rich` tables and `rich` progress bars. Never plain print in CLI code.

---

## 6. Data Models

### AgentSpan (in-memory, not stored directly)

```python
@dataclass
class AgentSpan:
    run_id:       str
    agent_name:   str
    input:        Any
    output:       Any
    duration_ms:  float
    tool_calls:   list[ToolCall]
    tokens_used:  Optional[int]
    model:        Optional[str]
    success:      bool
    failure_type: Optional[FailureType]
    failure_msg:  Optional[str]
    exception:    Optional[str]        # full traceback string
    timestamp:    float
    metadata:     dict
```

### ToolCall

```python
@dataclass
class ToolCall:
    tool_name:   str
    params:      dict
    result:      Any
    duration_ms: float
    error:       Optional[str]
    timestamp:   float
```

### GoldenCase

```python
@dataclass
class GoldenCase:
    id:           str
    span:         AgentSpan
    human_label:  bool
    human_notes:  str
    difficulty:   Literal["easy", "medium", "hard", "adversarial"]
    created_at:   datetime
    reviewed_by:  str
```

---

## 7. Failure Taxonomy

Full reference table. Every `FailureType` must be tested in `test_classifier.py`.

| FailureType | Trigger condition | Example |
|---|---|---|
| `WRONG_TOOL` | Agent called a semantically irrelevant tool | Weather query → calls `send_email` |
| `BAD_PARAMS` | Tool rejected due to invalid parameters | `search(query=None)` |
| `MISSING_TOOL` | Tool name not in allowed toolset | Calls `get_stock_price` but it wasn't registered |
| `TOOL_TIMEOUT` | Tool call exceeded timeout | `fetch_url` times out after 30s |
| `TOOL_API_ERROR` | Tool returned HTTP error | 429 rate limit, 500 server error |
| `HALLUCINATED_CALL` | Tool called that doesn't exist in any toolset | Calls `browse_web` when no browser tool available |
| `CONTEXT_OVERFLOW` | Token count > threshold mid-run | 128k context exceeded |
| `INFINITE_LOOP` | Same (tool, params) repeated ≥ N times | Calls `search("weather Delhi")` 5 times |
| `WRONG_FORMAT` | Output doesn't match expected schema | JSON expected, markdown returned |
| `TASK_FAILED` | Run completed, output is wrong | Answer is factually incorrect |
| `PARTIAL_SUCCESS` | Some subtasks done, not all | Booked flight but not hotel |
| `REFUSED` | LLM declined to complete | "I cannot help with that" |
| `EXCEPTION` | Python exception raised | `KeyError`, `AttributeError` |
| `TIMEOUT` | Full run wall-clock timeout | 30s limit exceeded |
| `UNKNOWN` | None of the above matched | Classifier couldn't determine reason |

---

## 8. API Contracts

### Base URL

Development: `http://localhost:8000`
Production: configurable via `AGENTPROBE_API_URL` env var

### Headers

```
Content-Type: application/json
X-API-Key: <key>    # optional, only if auth enabled
```

### Error format

```json
{
  "error": "run_not_found",
  "message": "No run with id abc-123",
  "status_code": 404
}
```

### Pagination

All list endpoints use `limit` + `offset`. Response always includes `total: int`.

---

## 9. Build Phases

### Month 1 — Core Engine (the thing that must work)

**Goal:** `@probe` decorator classifies failures and saves to SQLite. Basic dashboard shows run history.

**Week 1:**
- [ ] Repo setup: `pyproject.toml`, directory structure, `pre-commit` hooks
- [ ] `agentprobe/classifier/taxonomy.py` — `FailureType` enum, all 15 types, descriptions
- [ ] `agentprobe/classifier/rules/` — all 4 rule files
- [ ] `agentprobe/classifier/classifier.py` — `FailureClassifier` with priority order
- [ ] `tests/test_classifier.py` — at least 2 tests per `FailureType` (30 tests minimum)
- [ ] `agentprobe/storage/models.py` + `db.py` — SQLite working
- [ ] `agentprobe/decorator.py` — `@probe` writes spans to SQLite

**Week 2:**
- [ ] `api/main.py` + `api/routes/runs.py` + `api/routes/failures.py`
- [ ] Streamlit dashboard: run table + failure type breakdown (single `dashboard_v1.py` file, not Next.js yet)
- [ ] `docker-compose.yml` — api + sqlite volume
- [ ] `README.md` — 3-line quickstart working end-to-end

**Week 3:**
- [ ] `agentprobe/tracer.py` — batched async queue (100ms flush or 50 items)
- [ ] `api/routes/eval.py` — stub endpoints (returns mock data for now)
- [ ] Begin migrating Streamlit → Next.js dashboard skeleton

**Week 4:**
- [ ] Next.js dashboard: overview page + run detail page
- [ ] `agentprobe/config.py` — `ProbeConfig` with `configure()` function
- [ ] End-to-end test: real LangChain agent + `@probe` → failure classified → shown in dashboard

---

### Month 2 — Meta-Evaluation

**Goal:** LLM judge + golden dataset + judge accuracy scoring.

- [ ] `agentprobe/evaluator/judge.py` — LLM-as-judge with JSON output
- [ ] `agentprobe/evaluator/golden_dataset.py` — JSONL load/save
- [ ] `agentprobe/evaluator/meta_eval.py` — bootstrap CI on judge accuracy
- [ ] `agentprobe/evaluator/confidence.py` — flag low-confidence runs for review
- [ ] `api/routes/eval.py` — real endpoints (no more mocks)
- [ ] `api/routes/golden.py` — CRUD
- [ ] Dashboard: `/eval` page, `/review` page
- [ ] Build initial golden dataset: 50 human-labelled cases manually
- [ ] Run first meta-eval, document accuracy in README

---

### Month 3 — Regression CI

**Goal:** GitHub Actions fails on accuracy regression. A/B comparison with stats.

- [ ] `agentprobe/regression/stats.py` — bootstrap CI + McNemar test
- [ ] `agentprobe/regression/runner.py` — YAML test suite loader
- [ ] `agentprobe/regression/baseline.py` — snapshot and compare
- [ ] `agentprobe/regression/alert.py` — Slack webhook (optional)
- [ ] `.github/workflows/eval.yml` — runs regression suite on every PR
- [ ] `api/routes/compare.py` — A/B endpoint
- [ ] Dashboard: `/compare` page with CI bars
- [ ] `probe_tests.yml` — write 20 test cases for the demo agent

---

### Month 4 — Polish & Launch

**Goal:** `pip install agentprobe` works. Docs. Demo video. Open source.

- [ ] `cli/main.py` — all 6 CLI commands working
- [ ] Replace SQLite with Postgres in `docker-compose.yml`
- [ ] `Dockerfile.api` — production-ready
- [ ] `pyproject.toml` — `pip install agentprobe` publishes to PyPI (Test PyPI first)
- [ ] README: full docs, GIF demo, badge shields
- [ ] 3-minute Loom demo video (A/B comparison + regression caught by CI)
- [ ] GitHub release v0.1.0

---

## 10. Testing Strategy

### Unit tests (`tests/`)

**`test_classifier.py` — required tests:**

```python
# At minimum, one test per FailureType
def test_classifies_exception():
    span = make_span(exception="RuntimeError: API failed")
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.EXCEPTION

def test_classifies_timeout():
    span = make_span(exception="asyncio.TimeoutError: ...")
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.TIMEOUT

def test_classifies_infinite_loop():
    calls = [make_tool_call("search", {"q": "weather"}) for _ in range(4)]
    span = make_span(tool_calls=calls, success=False)
    ftype, _ = classifier.classify(span)
    assert ftype == FailureType.INFINITE_LOOP

def test_success_returns_none():
    span = make_span(success=True, output="The weather is 38C")
    ftype, msg = classifier.classify(span)
    assert ftype is None
    assert msg == "success"

# ... continue for all 14 failure types
```

**`test_meta_eval.py`:**
```python
def test_meta_eval_perfect_judge():
    # A judge that always agrees with human labels → accuracy = 1.0
    ...

def test_meta_eval_random_judge():
    # A judge at chance → accuracy ≈ 0.5, CI should contain 0.5
    ...

def test_bootstrap_ci_width_increases_with_less_data():
    # More data → narrower CI
    ...
```

**`test_regression.py`:**
```python
def test_no_regression_when_same():
    ...

def test_regression_detected_on_5pct_drop():
    ...

def test_no_alert_when_not_significant():
    # delta is 6% but p=0.4 → should NOT flag as regression
    ...
```

### Integration tests

- `tests/test_api.py` — uses `httpx.AsyncClient` against a real FastAPI test app
- Covers all routes with real SQLite in-memory database

### Test fixtures (`tests/fixtures/`)

Provide at least 5 JSON files representing real agent spans:
- `span_success.json`
- `span_wrong_tool.json`
- `span_infinite_loop.json`
- `span_exception.json`
- `span_context_overflow.json`

---

## 11. Configuration

### `pyproject.toml`

```toml
[project]
name = "agentprobe"
version = "0.1.0"
description = "Failure classification and meta-evaluation for LLM agents"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0",
    "sqlalchemy[asyncio]>=2.0",
    "aiosqlite",
    "fastapi>=0.110",
    "uvicorn[standard]",
    "anthropic>=0.25",
    "openai>=1.30",
    "scipy>=1.12",
    "numpy>=1.26",
    "typer>=0.12",
    "rich>=13",
    "httpx>=0.27",
    "pyyaml>=6",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "pre-commit", "ruff"]
dashboard = ["streamlit>=1.35"]  # month 1 only

[project.scripts]
probe = "agentprobe.cli.main:app"

[tool.pytest.ini_options]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
target-version = "py311"
```

### `docker-compose.yml`

```yaml
services:
  api:
    build:
      context: .
      dockerfile: Dockerfile.api
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://probe:probe@db:5432/agentprobe
    depends_on:
      - db

  dashboard:
    build:
      context: ./dashboard
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000

  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: probe
      POSTGRES_PASSWORD: probe
      POSTGRES_DB: agentprobe
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

---

## 12. Packaging & Distribution

### PyPI release checklist (month 4)

1. All tests passing (`pytest tests/ -v`)
2. `ruff check agentprobe/` clean
3. Version bumped in `pyproject.toml` and `agentprobe/__init__.py`
4. `python -m build` succeeds
5. Upload to Test PyPI first: `twine upload --repository testpypi dist/*`
6. `pip install -i https://test.pypi.org/simple/ agentprobe` in a fresh venv
7. Run quickstart from README — must work end to end
8. Upload to production PyPI: `twine upload dist/*`

### Version strategy

Use semantic versioning: `MAJOR.MINOR.PATCH`
- `0.x.x` — pre-1.0, breaking changes allowed between minors
- `1.0.0` — when meta-eval + regression CI are stable and documented

---

## 13. CI/CD Pipeline

### `.github/workflows/eval.yml`

```yaml
name: AgentProbe Regression CI

on:
  pull_request:
    branches: [main]

jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install AgentProbe
        run: pip install -e ".[dev]"

      - name: Run unit tests
        run: pytest tests/ -v --tb=short

      - name: Run regression suite
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: probe run --suite probe_tests.yml --fail-on-regression

      - name: Upload eval report
        uses: actions/upload-artifact@v4
        with:
          name: eval-report
          path: agentprobe_report.json
```

**`--fail-on-regression` flag behaviour:**
- Exit code 0 if no regression detected
- Exit code 1 if accuracy drop > threshold AND statistically significant
- Exit code 0 (with warning) if drop > threshold but NOT significant (print warning to stderr)

---

## 14. Environment Variables

| Variable | Default | Description |
|---|---|---|
| `AGENTPROBE_DB_URL` | `sqlite+aiosqlite:///agentprobe.db` | Database connection string |
| `AGENTPROBE_API_URL` | `None` | Remote API endpoint for span emission |
| `AGENTPROBE_JUDGE_MODEL` | `claude-haiku-4` | Model used for LLM judge |
| `AGENTPROBE_EMIT_CONSOLE` | `true` | Print spans to stdout |
| `AGENTPROBE_LOOP_THRESHOLD` | `3` | Repeated calls before INFINITE_LOOP fires |
| `OPENAI_API_KEY` | — | Required only for OpenAI judge |
| `ANTHROPIC_API_KEY` | — | Required only for Claude judge |
| `AGENTPROBE_API_KEY` | — | Optional auth for the FastAPI server |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Dashboard → API base URL |

---

## 15. Coding Conventions

### Python

- Type hints everywhere. No untyped functions.
- `async/await` for all I/O. No blocking calls in async functions.
- Pydantic v2 models for all API request/response bodies.
- SQLAlchemy 2.0 style (`select()`, not `query()`).
- `dataclasses` for internal data structures, Pydantic for API-facing ones.
- Exceptions: catch broad → log → re-raise specific. Never `except: pass`.
- Module-level logger: `logger = logging.getLogger(__name__)`.
- All public functions and classes must have docstrings.

### File organisation rules

- One class per file unless the classes are tiny (< 20 lines) and tightly related.
- `__init__.py` files export only what external code should use — no implementation details.
- `tests/` mirrors the `agentprobe/` structure exactly.

### Naming

| Thing | Convention | Example |
|---|---|---|
| Classes | PascalCase | `FailureClassifier` |
| Functions | snake_case | `classify_failure` |
| Constants | UPPER_SNAKE | `LOOP_THRESHOLD` |
| Files | snake_case | `loop_detector.py` |
| Pydantic models | PascalCase + `Schema` suffix | `RunSchema` |
| DB ORM models | PascalCase, no suffix | `Run`, `ToolCallRecord` |

### Git

- Branch naming: `feat/classifier-rules`, `fix/loop-detection`, `chore/pyproject-setup`
- Commit messages: `feat:`, `fix:`, `test:`, `docs:`, `chore:` prefixes
- Never commit directly to `main` — always PR
- PR must pass all unit tests before merge

---

## 16. What NOT to Build

> **Coding agent: do not implement any of the following unless explicitly asked.**

- ❌ Synchronous `@probe` decorator (async only for now)
- ❌ LangChain-specific integrations or callbacks (must be framework-agnostic)
- ❌ Cloud storage or remote database sync (local-first, always)
- ❌ User authentication system (API key header is enough)
- ❌ Multi-tenancy or organisation/team features
- ❌ Streaming evaluation (evaluate full run only, not token-by-token)
- ❌ Real-time WebSocket dashboard (polling every 5s is enough)
- ❌ Automatic prompt improvement suggestions
- ❌ A/B testing infrastructure (only compare existing runs, don't run experiments)
- ❌ Any third-party SaaS integrations except Slack webhook for alerts
- ❌ Mobile app or native desktop app
- ❌ Plugin system or extension marketplace
- ❌ Hindi/regional language support in v0.x (build generic first)

---

## Appendix: Quick Reference

### The 3-line user experience (must work by end of month 1)

```python
from agentprobe import probe

@probe(name="my-agent")
async def run(query: str) -> str:
    return await my_existing_agent.arun(query)
```

### The interview answer (write this in README by week 2)

> "I built this because LangSmith shows you *what* happened in your agent run. AgentProbe tells you *why* it failed. The classifier labels every failure into one of 14 types with zero LLM calls. The meta-evaluator tells you how accurate your LLM judge actually is — a number nobody else surfaces. And the regression CI means your PRs fail automatically if accuracy drops, just like unit tests."

### The one feature that differentiates everything

**Meta-evaluation.** Build it properly in month 2. The ability to say "my judge is 91% accurate ±4% on 100 labelled cases" is what makes this a serious tool, not a demo.

---

*Last updated: June 2026 | Version: 0.1.0-spec*
