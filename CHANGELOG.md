# Changelog

All notable changes to FailProbe are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026

### Added

- **Free heuristic judge (default)** — the meta-eval judge now defaults to a
  pure-Python `heuristic` engine that scores runs with no LLM call and **no API
  key**, using refusal/error markers and token-overlap signals. FailProbe is now
  fully usable end to end at zero cost.
- **OpenAI-compatible judge endpoints** — non-`claude`, non-`heuristic` judge
  models route to an OpenAI-compatible SDK, so you can point the judge at a
  local or self-hosted LLM (Ollama, vLLM, LM Studio, …) via the new
  `judge_base_url` config field / `FAILPROBE_JUDGE_BASE_URL` env var. `claude*`
  models still route to the Anthropic SDK.
- **`examples/support_agent/`** — a deterministic, key-free demo agent plus a
  13-case regression suite that exercises every classifier branch and the
  statistical regression gate end to end.

### Changed

- `judge_model` now defaults to `"heuristic"` (was an LLM model). Pass an
  explicit `model` (e.g. `claude-haiku-4`) on the CLI/API or set it via
  `configure(ProbeConfig(judge_model=...))` to use an LLM judge.
- New `judge_api_key` config field (env `FAILPROBE_JUDGE_API_KEY`, falling back
  to `OPENAI_API_KEY`) supplies credentials for the OpenAI-compatible path; any
  non-empty value works for local servers like Ollama.

## [0.2.1] - 2026

### Fixed

- Project metadata URLs now point at the renamed GitHub repository
  (`github.com/Avinash15042002/failprobe`) instead of the old `AgentProbe` path.

## [0.2.0] - 2026

First stable public release under the **`failprobe`** name.

### Added

- **`@probe` decorator** — wraps any `async` agent entry point, captures the
  run as an `AgentSpan`, and persists it fire-and-forget (`asyncio.create_task`)
  so FailProbe never blocks or alters your agent's output or exceptions.
- **Rule-based `FailureClassifier`** — classifies failures into a fixed taxonomy
  of 14 types (plus an `unknown` fallback) using only string matching,
  fingerprinting, and counters — **zero LLM or network calls**, sub-10ms.
- **Async tracer + storage** — SQLAlchemy 2.0 (async) models with Alembic
  migrations, backed by SQLite out of the box and PostgreSQL via the
  `failprobe[postgres]` extra.
- **LLM judge + meta-evaluation** — scores your evaluator against a
  human-labelled golden dataset and reports judge accuracy with a bootstrapped
  95% confidence interval.
- **Regression CI** — bootstrap confidence intervals and McNemar's exact test
  gate pull requests: the runner exits `1` only when an accuracy drop is *both*
  over threshold *and* statistically significant (p < 0.05); over-threshold but
  non-significant drops exit `0` with a warning.
- **FastAPI server** (`api/`) — REST endpoints for runs, failures, comparison,
  evaluation, golden dataset, and the review queue.
- **Next.js dashboard** (`dashboard/`) — overview and run-detail views polling
  the API.
- **Typer CLI** (`probe`) — six commands: `run`, `report`, `compare`,
  `baseline save`/`baseline list`, `meta-eval`, and `dashboard`, all rendered
  with `rich` and statistically honest (deltas always carry a CI + significance
  verdict).
- **Docker** — `docker compose up` brings up the API, dashboard, and PostgreSQL.

### Changed

- Distribution and import package renamed to **`failprobe`** (was `agentprobe`).
  Use `pip install failprobe` and `from failprobe import probe`.
- Environment variables renamed from `AGENTPROBE_*` to `FAILPROBE_*`
  (e.g. `FAILPROBE_DB_URL`, `FAILPROBE_EMIT_CONSOLE`).

### Known Limitations

- **Async only** — sync `@probe` support is not yet implemented.
- **No streaming evaluation** — the LLM judge scores complete runs, not token
  streams.
- **SQLite / PostgreSQL only** — no other database backends.
- **Meta-eval accuracy is unpublished** — the initial golden dataset requires a
  manual labelling pass before a headline judge-accuracy number can be reported.

### Upcoming

- Sync `@probe` support.
- Framework-specific integrations (e.g. LangChain callbacks).
- A published golden dataset and headline judge-accuracy number.

## [0.1.0] - 2026

Initial release. Superseded by 0.2.0 and yanked from PyPI; it used the
`agentprobe` import name, which 0.2.0 renames to `failprobe`.
