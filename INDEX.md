# AgentProbe — Task Index

> One file per feature/task. Read each file fully before starting that task.
> Build in the order listed — later tasks depend on earlier ones.

---

## Month 1 — Core Engine

| File | Task | Phase |
|---|---|---|
| `TASK_01_repo_setup.md` | Repo scaffolding, `pyproject.toml`, `pre-commit` | Week 1 |
| `TASK_03_data_models.md` | `AgentSpan`, `ToolCall`, `GoldenCase` dataclasses | Week 1 |
| `TASK_04_failure_taxonomy.md` | `FailureType` enum + descriptions | Week 1 |
| `TASK_05_failure_classifier.md` | `FailureClassifier` + all 4 rule modules | Week 1 |
| `TASK_06_storage_layer.md` | SQLAlchemy ORM models, async DB engine, Alembic | Week 1 |
| `TASK_07_probe_decorator.md` | `@probe` decorator | Week 1 |
| `TASK_09_fastapi_server.md` | FastAPI routes (stub eval endpoints) | Week 2 |
| `TASK_10_streamlit_dashboard_v1.md` | Streamlit dashboard (temporary) | Week 2 |
| `TASK_17_docker_infra.md` | Dev `docker-compose.yml` (SQLite) | Week 2 |
| `TASK_08_async_tracer.md` | Batched async span emitter | Week 3 |
| `TASK_11_nextjs_dashboard.md` | Next.js skeleton + Overview + Run Detail pages | Week 3–4 |
| `TASK_02_probe_config.md` | `ProbeConfig` singleton + `configure()` | Week 4 |

## Month 2 — Meta-Evaluation

| File | Task |
|---|---|
| `TASK_12_llm_judge.md` | LLM-as-judge (`judge.py` + prompts) |
| `TASK_13_meta_evaluation.md` | Meta-eval, golden dataset manager, confidence flagging |
| `TASK_11_nextjs_dashboard.md` | Complete `/eval` and `/review` pages (continued) |

## Month 3 — Regression CI

| File | Task |
|---|---|
| `TASK_14_regression_ci.md` | Stats, test runner, baseline, alert, GitHub Actions |
| `TASK_11_nextjs_dashboard.md` | Complete `/compare` and `/failures` pages (continued) |

## Month 4 — Polish & Launch

| File | Task |
|---|---|
| `TASK_15_cli.md` | All 6 CLI commands |
| `TASK_17_docker_infra.md` | Upgrade to Postgres prod compose (continued) |
| `TASK_18_packaging_launch.md` | PyPI release, README, demo video |

## Testing (runs in parallel with everything)

| File | Task |
|---|---|
| `TASK_16_test_suite.md` | Full test suite (`test_classifier`, `test_meta_eval`, `test_regression`, `test_api`) |

---

## Dependency Graph

```
TASK_01 (scaffold)
  └── TASK_03 (data models)
        ├── TASK_04 (taxonomy)
        │     └── TASK_05 (classifier)  ← depends on 03 + 04
        └── TASK_06 (storage)
              └── TASK_07 (decorator)   ← depends on 03 + 04 + 05 + 06
                    └── TASK_08 (tracer) ← depends on 06 + 07
TASK_07 + TASK_06
  └── TASK_09 (API)                    ← depends on 06
        └── TASK_10 (Streamlit v1)     ← depends on 09
              └── TASK_11 (Next.js)    ← depends on 09
TASK_02 (config)    ← can be done any time after TASK_01

TASK_12 (judge)     ← depends on 03, 06 (Month 2+)
  └── TASK_13 (meta-eval) ← depends on 12

TASK_13 + TASK_06
  └── TASK_14 (regression) ← depends on 13 (Month 3+)
        └── TASK_15 (CLI)  ← depends on 09, 13, 14 (Month 4)

TASK_16 (tests)     ← runs alongside all tasks, Month 1+
TASK_17 (docker)    ← depends on 09 (Month 1 Week 2)
TASK_18 (launch)    ← depends on everything (Month 4)
```

---

*Last updated: June 2026 | Spec version: 0.1.0*
