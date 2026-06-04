# Task 06 — Storage Layer (`agentprobe/storage/`)

**Phase:** Month 1, Week 1
**Module:** `agentprobe/storage/models.py` + `agentprobe/storage/db.py` + Alembic migrations

---

## Goal

Implement the async SQLAlchemy ORM models, database engine factory, and Alembic migrations. Must support SQLite (dev, zero config) and PostgreSQL (prod, via env var).

---

## Files to Create

```
agentprobe/storage/
├── __init__.py
├── models.py           ← SQLAlchemy ORM models
├── db.py               ← engine factory, session management
└── migrations/         ← Alembic migration files
    ├── env.py
    └── versions/
```

---

## `models.py` — ORM Models

Use SQLAlchemy 2.0 style (`Mapped`, `mapped_column`). All primary keys are UUID strings.

```python
class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str]                    # UUID4, primary key
    agent_name: Mapped[str]
    input_text: Mapped[str]            # JSON-serialized input
    output_text: Mapped[Optional[str]]
    duration_ms: Mapped[float]
    tokens_used: Mapped[Optional[int]]
    model: Mapped[Optional[str]]
    success: Mapped[bool]
    failure_type: Mapped[Optional[str]]   # FailureType.value
    failure_msg: Mapped[Optional[str]]
    exception: Mapped[Optional[str]]
    tags: Mapped[str]                  # JSON-serialized dict
    created_at: Mapped[datetime]

class ToolCallRecord(Base):
    __tablename__ = "tool_calls"
    id: Mapped[str]                    # UUID4
    run_id: Mapped[str]                # FK → runs.id
    tool_name: Mapped[str]
    params: Mapped[str]                # JSON
    result: Mapped[Optional[str]]      # JSON
    duration_ms: Mapped[float]
    error: Mapped[Optional[str]]
    timestamp: Mapped[datetime]

class EvalResult(Base):
    __tablename__ = "eval_results"
    id: Mapped[str]
    run_id: Mapped[str]                # FK → runs.id
    judge_model: Mapped[str]
    score: Mapped[float]
    reasoning: Mapped[str]
    confidence: Mapped[float]
    human_label: Mapped[Optional[bool]]
    human_notes: Mapped[Optional[str]]
    created_at: Mapped[datetime]

class RegressionBaseline(Base):
    __tablename__ = "regression_baselines"
    id: Mapped[str]
    name: Mapped[str]                  # e.g. "main-branch-v1.2"
    metrics: Mapped[str]               # JSON: {accuracy, avg_score, failure_rate, avg_cost}
    n_runs: Mapped[int]
    created_at: Mapped[datetime]
```

---

## `db.py` — Database Engine

```python
async def get_engine(db_url: str) -> AsyncEngine: ...

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager — use as `async with get_session() as session:`"""
    ...

async def init_db() -> None:
    """Creates all tables if they don't exist. Called once on startup."""
    ...
```

### Rules

- Use `create_async_engine` with `echo=False` (no SQL logging by default).
- Session factory must use `expire_on_commit=False` (important for async).
- `init_db()` calls `Base.metadata.create_all()` — safe to call multiple times.
- Engine is a module-level singleton once initialized; `get_session()` yields from it.

---

## Alembic Setup

- `alembic.ini` in repo root, pointing to `agentprobe/storage/migrations/`
- `migrations/env.py` imports `Base` from `agentprobe.storage.models` and uses `run_async_migrations()`
- First migration: `versions/0001_initial_schema.py` — creates all four tables

---

## Acceptance Criteria

- [ ] `await init_db()` creates all four tables in a fresh SQLite file
- [ ] `async with get_session() as s:` yields a usable `AsyncSession`
- [ ] `Run`, `ToolCallRecord`, `EvalResult`, `RegressionBaseline` all have correct columns
- [ ] ORM models use SQLAlchemy 2.0 style (`select()`, not `session.query()`)
- [ ] Connection string defaults to SQLite; swapping to Postgres requires only changing `AGENTPROBE_DB_URL` env var
- [ ] `alembic upgrade head` runs successfully against a fresh SQLite DB
