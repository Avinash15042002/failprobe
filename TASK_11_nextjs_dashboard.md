# Task 11 — Next.js Dashboard (`dashboard/`)

**Phase:** Month 1 Week 3–4 (skeleton) → Month 2 (full pages)
**Module:** `dashboard/`

---

## Goal

Build the production Next.js dashboard that replaces Streamlit. Uses App Router, Shadcn/UI, Recharts, and SWR for polling. Polls the API every 5 seconds — no WebSockets.

---

## Stack

| Layer | Choice |
|---|---|
| Framework | Next.js 15 (App Router) |
| UI | Shadcn/UI + Tailwind CSS |
| Charts | Recharts |
| State | Zustand |
| API client | `fetch` + SWR |

---

## Directory Structure

```
dashboard/
├── package.json
├── next.config.ts
├── tailwind.config.ts
└── app/
    ├── layout.tsx
    ├── page.tsx               ← Overview
    ├── runs/
    │   └── [id]/page.tsx      ← Run Detail
    ├── failures/
    │   └── page.tsx           ← Failure Analytics
    ├── eval/
    │   └── page.tsx           ← Evaluation
    ├── compare/
    │   └── page.tsx           ← A/B Comparison
    └── review/
        └── page.tsx           ← Human Review Queue
```

---

## Page Specifications

### `/` — Overview

- Table of recent runs: `agent_name`, `status (✓/✗)`, `failure_type`, `duration_ms`, `tokens`, `created_at`
- Failure rate sparkline (last 7 days) — Recharts `LineChart`
- Top 3 failure types as pill badges with counts

### `/runs/[id]` — Run Detail

- Header: agent name, input, output, duration, model, tags
- Trace timeline: horizontal waterfall chart of tool calls with duration bars (Recharts `BarChart` horizontal)
- Failure card: type badge, explanation text, raw exception if present
- Eval result section: judge score bar, reasoning text, confidence indicator

### `/failures` — Failure Analytics

- Taxonomy heatmap: FailureType on Y-axis, time buckets on X-axis, cell = count
- Confusion matrix: shown only after meta-eval has been run
- Failure type distribution: bar chart sorted by frequency

### `/eval` — Evaluation

- Judge accuracy card: large number + ± CI range (e.g. "91% ± 4%")
- Golden dataset table: case ID, difficulty, human label, judge score, match/mismatch indicator
- "Run meta-eval" button → `POST /eval/run` on all golden cases
- "Add to golden dataset" button available on any run

### `/compare` — A/B Comparison

- Two multi-select dropdowns: baseline runs, candidate runs
- On compare: delta table with CI error bars (green positive, red negative)
- Significance indicator: "Statistically significant (p=0.02)" or "Not significant (p=0.34)"

### `/review` — Human Review Queue

- Table of flagged runs (judge confidence < 0.6 OR judge-human disagreement)
- Each row: input text, output text, judge score
- Pass / Fail buttons + notes textarea
- On submit: `POST /review/{run_id}` with `{ label, notes }`

---

## API Polling

```typescript
// All data fetched via SWR with 5-second refresh
const { data, error } = useSWR("/api/runs", fetcher, { refreshInterval: 5000 });

// API base URL from env
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
```

---

## Month 1 Deliverable (minimum)

Build only the skeleton + Overview page + Run Detail page. The other pages can be empty with a "Coming soon" placeholder.

---

## Acceptance Criteria

- [ ] `npm run dev` starts without errors
- [ ] Overview page loads and displays real runs from the API
- [ ] Run detail page renders trace timeline and failure card
- [ ] Data refreshes automatically every 5 seconds
- [ ] `NEXT_PUBLIC_API_URL` env var changes the API base URL
- [ ] Failures / Eval / Compare / Review pages complete by end of Month 2
