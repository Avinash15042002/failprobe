# Task 18 — Packaging & PyPI Launch

**Phase:** Month 4
**Module:** `pyproject.toml`, `README.md`, release workflow

---

## Goal

Make `pip install agentprobe` work from PyPI. Go through Test PyPI first, then production. Document the 3-line quickstart and produce the demo video.

---

## Pre-release Checklist

1. All tests passing: `pytest tests/ -v`
2. `ruff check agentprobe/` — zero errors
3. Version bumped in `pyproject.toml` AND `agentprobe/__init__.py`
4. `python -m build` succeeds and produces `dist/agentprobe-0.1.0.tar.gz`
5. Upload to Test PyPI: `twine upload --repository testpypi dist/*`
6. Fresh venv test: `pip install -i https://test.pypi.org/simple/ agentprobe`
7. Run the README quickstart end-to-end in the fresh venv — must work
8. Upload to production PyPI: `twine upload dist/*`

---

## Version Strategy

Use semantic versioning: `MAJOR.MINOR.PATCH`

- `0.x.x` — pre-1.0, breaking changes allowed between minors
- `1.0.0` — when meta-eval + regression CI are stable and documented

---

## `README.md` Requirements

### Sections (in order)

1. **One-line pitch** — "AgentProbe tells you *why* your LLM agent failed, not just that it did."
2. **Install** — `pip install agentprobe`
3. **Quickstart** — the 3-line example, must work end-to-end:
   ```python
   from agentprobe import probe

   @probe(name="my-agent")
   async def run_agent(query: str) -> str:
       return await your_existing_agent.arun(query)
   ```
4. **What you get** — failure taxonomy table, meta-eval description, regression CI description
5. **Dashboard** — screenshot or GIF of the Overview page
6. **CLI reference** — all 6 commands with brief descriptions
7. **Configuration** — `ProbeConfig` fields table
8. **How it differs from LangSmith/LangFuse** — one paragraph
9. **Contributing** — link to `CONTRIBUTING.md`

### README badges (top of file)

```markdown
![PyPI](https://img.shields.io/pypi/v/agentprobe)
![Python](https://img.shields.io/pypi/pyversions/agentprobe)
![License](https://img.shields.io/github/license/Avinash15042002/agentprobe)
![Tests](https://github.com/Avinash15042002/agentprobe/actions/workflows/eval.yml/badge.svg)
```

---

## Demo Video (Loom, 3 minutes)

Script outline:

1. **(0:00–0:30)** — Problem statement: "LangSmith shows you what happened. AgentProbe shows you why."
2. **(0:30–1:00)** — Add `@probe` to an existing agent (15 seconds of code), run it, show console output
3. **(1:00–1:45)** — Dashboard: overview table, click into a failed run, show the INFINITE_LOOP card with explanation
4. **(1:45–2:30)** — Meta-eval: show the judge accuracy panel ("91% ±4% on 50 cases")
5. **(2:30–3:00)** — Regression CI: show a GitHub Actions run that failed because accuracy dropped, show the PR comment

---

## GitHub Release

Tag: `v0.1.0`  
Release notes should include:
- What's included (classifier, meta-eval, regression CI, dashboard, CLI)
- Breaking changes (none for 0.1.0)
- Known limitations (async only, no streaming eval, SQLite/Postgres only)

---

## Acceptance Criteria

- [ ] `pip install agentprobe` installs successfully from PyPI
- [ ] `from agentprobe import probe, ProbeConfig` works in a fresh venv
- [ ] The 3-line quickstart in README runs end-to-end
- [ ] README has all 9 sections above
- [ ] `python -m build` produces a clean sdist + wheel
- [ ] GitHub release `v0.1.0` exists with release notes
