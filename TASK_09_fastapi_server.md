# Task 09 — FastAPI Server (`api/`)

**Phase:** Month 1, Week 2
**Module:** `api/main.py` + `api/routes/` + `api/schemas.py`

---

## Goal

Implement the REST API that the dashboard and CLI query. All routes are async. Auth is optional (off by default).

---

## Files to Create

```
api/
├── main.py         ← FastAPI app, CORS, lifespan
├── schemas.py      ← Pydantic response models
└── routes/
    ├── __init__.py
    ├── runs.py     ← GET /runs, GET /runs/{id}
    ├── failures.py ← GET /failures, GET /failures/taxonomy
    ├── eval.py     ← POST /eval/run, GET /eval/judge-accuracy
    ├── compare.py  ← POST /compare
    └── golden.py   ← CRUD /golden
```

---

## `main.py`

```python
app = FastAPI(title="AgentProbe API", version="0.1.0")

# CORS: allow localhost:3000 (dashboard) by default
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], ...)

# Lifespan: call storage.init_db() on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

# Health check
@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
```

---

## Route Specifications

### `GET /runs`

```
Query params: agent_name, success (bool), failure_type, limit=50, offset=0, order="desc"
Response: { total: int, runs: Run[] }
```

### `GET /runs/{run_id}`

```
Response: { run: Run, tool_calls: ToolCallRecord[], eval_result: EvalResult | null }
404 if not found.
```

### `GET /failures/taxonomy`

```
Response: {
  breakdown: { [FailureType]: { count: int, description: str, pct: float } },
  total_failures: int,
  total_runs: int,
  failure_rate: float
}
```

### `GET /failures`

```
Query: agent_name, failure_type, from_date, to_date, limit, offset
Response: { total: int, failures: FailureEvent[] }
```

### `POST /eval/run`

```
Body: { run_id: str, model?: str }
Response: EvalResult
```
**Month 1:** return a stub `EvalResult` with `score=0.0, reasoning="eval not yet implemented"`.
**Month 2:** replace with real judge call.

### `GET /eval/judge-accuracy`

```
Response: MetaEvalReport | { error: "no_golden_dataset" }
```

### `POST /compare`

```
Body: {
  baseline_run_ids: str[],
  candidate_run_ids: str[],
  metric: "accuracy" | "score" | "cost"
}
Response: {
  baseline_mean, candidate_mean, delta,
  ci_lower, ci_upper, p_value, is_significant,
  n_baseline, n_candidate
}
```

### `GET /golden`, `POST /golden`, `PATCH /golden/{id}`, `DELETE /golden/{id}`

Standard CRUD for `GoldenCase` records.

### `GET /review/queue`

```
Response: { cases: AgentSpan[] }  # spans flagged for human review
```

### `POST /review/{run_id}`

```
Body: { label: bool, notes: str }
# Saves to golden dataset, removes from review queue
```

---

## Error format (all routes)

```json
{
  "error": "run_not_found",
  "message": "No run with id abc-123",
  "status_code": 404
}
```

---

## Pagination

All list endpoints: `limit` + `offset`. Response always includes `total: int`.

---

## Optional Auth

If `AGENTPROBE_API_KEY` env var is set:
- Require `X-API-Key: <key>` header on all non-health routes
- Return 401 if missing or wrong

If env var is not set, auth is disabled entirely.

---

## Acceptance Criteria

- [ ] `GET /health` returns `200 {"status": "ok"}` without DB connection
- [ ] `GET /runs` returns paginated results with correct total
- [ ] `GET /runs/{bad-id}` returns `404` in the standard error format
- [ ] `POST /eval/run` returns a stub result in Month 1 (no LLM call)
- [ ] All routes have async handlers (`async def`)
- [ ] CORS allows requests from `localhost:3000`
- [ ] Tests in `tests/test_api.py` pass using `httpx.AsyncClient` + in-memory SQLite
