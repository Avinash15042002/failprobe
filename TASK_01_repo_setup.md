# Task 01 — Repo Setup & Project Configuration

**Phase:** Month 1, Week 1
**Module:** Root / `pyproject.toml` / `alembic.ini`

---

## Goal

Bootstrap the repository with all tooling, config files, and directory scaffolding so every subsequent task has a clean, working foundation to build on.

---

## Deliverables

### Directory structure to create

```
agentprobe/                    ← repo root
├── agentprobe/                ← pip package (empty __init__.py for now)
│   ├── __init__.py
│   ├── classifier/
│   ├── evaluator/
│   ├── storage/
│   └── regression/
├── api/
│   └── routes/
├── dashboard/
├── cli/
├── tests/
│   └── fixtures/
└── .github/
    └── workflows/
```

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
dashboard = ["streamlit>=1.35"]

[project.scripts]
probe = "agentprobe.cli.main:app"

[tool.pytest.ini_options]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
target-version = "py311"
```

### `alembic.ini`

Standard Alembic config pointing at `agentprobe/storage/migrations/`.

### `pre-commit` config

`.pre-commit-config.yaml` with `ruff` linter + formatter hooks.

---

## Acceptance Criteria

- [ ] `pip install -e ".[dev]"` succeeds in a fresh Python 3.11 venv
- [ ] `ruff check agentprobe/` passes with zero errors
- [ ] `pytest tests/` exits 0 (no tests yet = no failures)
- [ ] All subdirectories exist with at least an empty `__init__.py`
- [ ] `pre-commit run --all-files` passes

---

## Notes

- Python 3.11+ is required (uses `match` statements and newer `asyncio` features)
- Do NOT add any implementation code here — this task is scaffolding only
