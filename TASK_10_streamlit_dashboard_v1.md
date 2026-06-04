# Task 10 — Streamlit Dashboard v1 (`dashboard_v1.py`)

**Phase:** Month 1, Week 2
**Module:** `dashboard_v1.py` (single file at repo root, temporary)

---

## Goal

Build a working Streamlit dashboard to visualise run history and failure breakdowns. This is the Month 1 throwaway — it will be replaced by Next.js in Month 2. Keep it in a single file. Do not spend time on aesthetics.

---

## Pages / Sections

This is a **single-page Streamlit app** with sections, not a multi-page app.

### Section 1 — Run History Table

- Query `GET /runs?limit=100` from the local API
- Display as a `st.dataframe` with columns: `agent_name`, `status (✓/✗)`, `failure_type`, `duration_ms`, `tokens_used`, `created_at`
- Add a sidebar filter for `agent_name` and `success` (pass/fail toggle)

### Section 2 — Failure Breakdown

- Query `GET /failures/taxonomy`
- Display a `st.bar_chart` of failure types sorted by count
- Below the chart: display top 3 failure types as `st.metric` cards

### Section 3 — Run Detail (expandable)

- Add a `st.selectbox` to pick a run ID from the table
- On selection, query `GET /runs/{id}` and show:
  - Input / Output text
  - Failure type badge + explanation
  - Tool calls as a sub-table (tool name, params, result, error)

---

## Implementation Notes

```python
import streamlit as st
import httpx

API_BASE = "http://localhost:8000"

def fetch(path: str) -> dict:
    r = httpx.get(f"{API_BASE}{path}")
    r.raise_for_status()
    return r.json()

st.title("AgentProbe — Run Monitor")
# ... sections follow
```

- Use `st.cache_data(ttl=5)` on API calls so the dashboard auto-refreshes every 5 seconds.
- Handle API unavailable gracefully: show `st.error("API not reachable")` instead of crashing.

---

## Running

```bash
streamlit run dashboard_v1.py
```

Add to `pyproject.toml` optional deps:
```toml
[project.optional-dependencies]
dashboard = ["streamlit>=1.35"]
```

---

## Acceptance Criteria

- [ ] `streamlit run dashboard_v1.py` launches without error
- [ ] Run table populates from live API data
- [ ] Failure breakdown chart renders correctly
- [ ] Run detail section shows tool calls when a run with tool calls is selected
- [ ] API unavailability shows an error message, not a Python traceback
- [ ] Auto-refreshes every 5 seconds via `st.cache_data(ttl=5)`

---

## Note

This file is **temporary**. Once the Next.js dashboard (Task 11) passes its acceptance criteria, `dashboard_v1.py` is deleted from the repo.
