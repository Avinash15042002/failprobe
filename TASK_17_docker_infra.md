# Task 17 — Docker & Infrastructure (`docker-compose.yml`, `Dockerfile.api`)

**Phase:** Month 1 Week 2 (SQLite dev compose) → Month 4 (Postgres prod compose)
**Module:** Root infrastructure files

---

## Goal

Containerise the API and dashboard so the entire stack runs with `docker compose up`. No mandatory external services — everything is self-hostable.

---

## Month 1 Deliverable — Dev Compose (SQLite)

```yaml
# docker-compose.yml (Month 1)
services:
  api:
    build:
      context: .
      dockerfile: Dockerfile.api
    ports:
      - "8000:8000"
    volumes:
      - ./agentprobe.db:/app/agentprobe.db   # persist SQLite file
    environment:
      - AGENTPROBE_DB_URL=sqlite+aiosqlite:////app/agentprobe.db
      - AGENTPROBE_EMIT_CONSOLE=true

  dashboard:
    build:
      context: ./dashboard
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
    depends_on:
      - api
```

---

## Month 4 Deliverable — Prod Compose (PostgreSQL)

```yaml
# docker-compose.yml (Month 4)
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

## `Dockerfile.api`

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml .
COPY agentprobe/ agentprobe/
COPY api/ api/
COPY alembic.ini .

RUN pip install -e "."

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `AGENTPROBE_DB_URL` | `sqlite+aiosqlite:///agentprobe.db` | Database connection string |
| `AGENTPROBE_API_URL` | `None` | Remote API endpoint for span emission |
| `AGENTPROBE_JUDGE_MODEL` | `claude-haiku-4` | Model for LLM judge |
| `AGENTPROBE_EMIT_CONSOLE` | `true` | Print spans to stdout |
| `AGENTPROBE_LOOP_THRESHOLD` | `3` | Repeated calls before INFINITE_LOOP fires |
| `OPENAI_API_KEY` | — | Required only for OpenAI judge |
| `ANTHROPIC_API_KEY` | — | Required only for Claude judge |
| `AGENTPROBE_API_KEY` | — | Optional auth for the FastAPI server |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Dashboard → API base URL |

---

## Acceptance Criteria

- [ ] `docker compose up` starts API on port 8000 and dashboard on port 3000
- [ ] `GET http://localhost:8000/health` returns 200
- [ ] Dashboard at `http://localhost:3000` loads and queries the API
- [ ] SQLite data persists across container restarts (via volume mount)
- [ ] Month 4: replacing SQLite compose with Postgres compose requires only swapping `docker-compose.yml`
- [ ] `Dockerfile.api` builds in < 60 seconds on a clean Docker cache
