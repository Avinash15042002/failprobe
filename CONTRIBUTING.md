# Contributing to FailProbe

Thanks for your interest in improving FailProbe! This guide covers the dev
setup and the gates every change must pass.

## Dev setup

```bash
git clone https://github.com/Avinash15042002/AgentProbe.git
cd AgentProbe
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Before you open a PR

Every change must pass these locally:

```bash
ruff check failprobe/ api/        # zero issues
pytest tests/                      # all green (the e2e test is excluded by default)
```

To run the end-to-end pipeline test explicitly:

```bash
pytest tests/test_e2e.py -m e2e
```

## Design principles

These are load-bearing — please respect them in any contribution:

- **Never block the agent.** Any failure inside FailProbe is caught, logged to
  stderr, and swallowed; the user's agent always gets its original result or
  exception. Span emission is fire-and-forget via `asyncio.create_task`.
- **The rule-based classifier makes zero LLM/network calls.** `failprobe/classifier/`
  uses only string matching, fingerprinting, and counters.
- **Statistical honesty.** Never show a delta without a confidence interval, and
  never call something a regression unless it is over threshold *and*
  statistically significant (p < 0.05).

## Layer ownership

| Layer | Owns | Must not touch |
|---|---|---|
| `failprobe/classifier/` | Rule-based classification | LLM calls, DB, network |
| `failprobe/evaluator/` | LLM judge, golden dataset, meta-eval | Span capture, classification |
| `failprobe/storage/` | ORM models, sessions, migrations | Business logic |
| `failprobe/regression/` | Stats, CI runner, baseline | Span capture, evaluation |
| `api/` | HTTP routes and schemas | Business logic (import from the package) |
| `failprobe/cli/` | Commands, rich output | Direct DB access (go via API or package) |

## Conventions

- Type hints and docstrings on all public functions and classes.
- Pydantic v2 models are `PascalCase` + `Schema` suffix; ORM models are
  `PascalCase` with no suffix.
- One concern per file; `__init__.py` exports only the public API.

By contributing, you agree that your contributions are licensed under the
project's [MIT License](LICENSE).
