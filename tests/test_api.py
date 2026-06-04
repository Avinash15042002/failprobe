"""Tests for the FailProbe REST API.

Each test runs the ASGI app in-process via ``httpx.AsyncClient`` +
``ASGITransport`` (no real network) against a fresh temporary SQLite database.
The DB singletons in ``storage.db`` are reset per test for isolation, mirroring
``test_storage.py``. ``init_db()`` is awaited in the fixture because
``ASGITransport`` does not run the app's lifespan.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from failprobe.classifier import FailureType
from failprobe.evaluator import judge as judge_mod
from failprobe.storage import db, get_session, init_db
from failprobe.storage.models import ReviewQueueItem, Run
from api.main import app

_VALID_JUDGE_JSON = '{"score": 0.8, "reasoning": "good", "confidence": 0.9, "key_issues": []}'


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch) -> AsyncClient:
    """Yield an AsyncClient bound to the app over a fresh temp SQLite DB."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("FAILPROBE_DB_URL", f"sqlite+aiosqlite:///{db_file.as_posix()}")
    monkeypatch.delenv("FAILPROBE_API_KEY", raising=False)
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_session_factory", None)
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _seed_run(**overrides) -> str:
    """Insert one Run and return its id."""
    defaults = {
        "agent_name": "weather-agent",
        "input_text": '"What is the weather?"',
        "output_text": '"Sunny."',
        "duration_ms": 42.0,
        "success": True,
        "tags": "{}",
    }
    async with get_session() as session:
        run = Run(**{**defaults, **overrides})
        session.add(run)
        await session.commit()
        return run.id


async def test_health(client: AsyncClient) -> None:
    """``GET /health`` returns 200 with status and version."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": "0.2.0"}


async def test_list_runs_empty(client: AsyncClient) -> None:
    """``GET /runs`` returns an empty, well-formed page when there are no runs."""
    resp = await client.get("/runs")
    assert resp.status_code == 200
    assert resp.json() == {"total": 0, "runs": []}


async def test_list_runs_returns_schema(client: AsyncClient) -> None:
    """``GET /runs`` returns runs matching the response schema."""
    await _seed_run()
    resp = await client.get("/runs")
    body = resp.json()
    assert resp.status_code == 200
    assert body["total"] == 1
    run = body["runs"][0]
    assert run["agent_name"] == "weather-agent"
    assert run["success"] is True
    assert run["tags"] == {}
    assert "created_at" in run


async def test_list_runs_filter_by_agent(client: AsyncClient) -> None:
    """The ``agent_name`` filter narrows the result set and total."""
    await _seed_run(agent_name="a")
    await _seed_run(agent_name="b")
    resp = await client.get("/runs", params={"agent_name": "a"})
    body = resp.json()
    assert body["total"] == 1
    assert body["runs"][0]["agent_name"] == "a"


async def test_run_detail(client: AsyncClient) -> None:
    """``GET /runs/{id}`` returns the run, empty tool calls, and null eval."""
    run_id = await _seed_run()
    resp = await client.get(f"/runs/{run_id}")
    body = resp.json()
    assert resp.status_code == 200
    assert body["run"]["id"] == run_id
    assert body["tool_calls"] == []
    assert body["eval_result"] is None


async def test_runs_bad_id_404(client: AsyncClient) -> None:
    """``GET /runs/{bad-id}`` returns 404 in the standard error envelope."""
    resp = await client.get("/runs/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body == {
        "error": "run_not_found",
        "message": "No run with id does-not-exist",
        "status_code": 404,
    }


async def test_taxonomy_all_15_types(client: AsyncClient) -> None:
    """``GET /failures/taxonomy`` always lists all 15 failure types."""
    resp = await client.get("/failures/taxonomy")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["breakdown"].keys()) == {ft.value for ft in FailureType}
    assert len(body["breakdown"]) == 15
    assert body["total_failures"] == 0
    assert body["total_runs"] == 0
    assert body["failure_rate"] == 0.0


async def test_taxonomy_counts_and_rate(client: AsyncClient) -> None:
    """Failed runs are counted under their type with a correct failure rate."""
    await _seed_run(success=True)
    await _seed_run(success=False, failure_type=FailureType.WRONG_TOOL.value)
    await _seed_run(success=False, failure_type=FailureType.WRONG_TOOL.value)
    resp = await client.get("/failures/taxonomy")
    body = resp.json()
    assert body["total_runs"] == 3
    assert body["total_failures"] == 2
    assert body["breakdown"][FailureType.WRONG_TOOL.value]["count"] == 2
    assert body["breakdown"][FailureType.WRONG_TOOL.value]["pct"] == 100.0
    assert body["failure_rate"] == round(2 / 3, 4)


async def test_list_failures(client: AsyncClient) -> None:
    """``GET /failures`` returns only failed runs."""
    await _seed_run(success=True)
    await _seed_run(success=False, failure_type=FailureType.TASK_FAILED.value)
    resp = await client.get("/failures")
    body = resp.json()
    assert body["total"] == 1
    assert body["failures"][0]["failure_type"] == FailureType.TASK_FAILED.value


async def test_eval_run_judges(client: AsyncClient, monkeypatch) -> None:
    """``POST /eval/run`` judges the run and persists the real evaluation.

    The judge's network seam is monkeypatched to return canned JSON, so the full
    judge → persist → fetch path runs without any LLM call.
    """
    async def _fake_call(prompt: str, model: str) -> str:
        return _VALID_JUDGE_JSON

    monkeypatch.setattr(judge_mod, "_call_llm", _fake_call)
    run_id = await _seed_run()

    resp = await client.post("/eval/run", json={"run_id": run_id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == run_id
    assert body["score"] == 0.8
    assert body["reasoning"] == "good"
    # The evaluation is persisted and surfaces in the run detail.
    detail = (await client.get(f"/runs/{run_id}")).json()
    assert detail["eval_result"]["score"] == 0.8


async def test_eval_run_missing_run_404(client: AsyncClient) -> None:
    """``POST /eval/run`` for an unknown run returns the standard 404."""
    resp = await client.post("/eval/run", json={"run_id": "nope"})
    assert resp.status_code == 404
    assert resp.json()["error"] == "run_not_found"


async def test_judge_accuracy_no_dataset(client: AsyncClient, monkeypatch, tmp_path) -> None:
    """``GET /eval/judge-accuracy`` reports the missing golden dataset."""
    monkeypatch.chdir(tmp_path)  # ensure no golden file in scope
    resp = await client.get("/eval/judge-accuracy")
    assert resp.status_code == 200
    assert resp.json() == {"error": "no_golden_dataset"}


async def test_compare_rejects_small_groups(client: AsyncClient) -> None:
    """``POST /compare`` returns 400 insufficient_data when a group has < 5 runs."""
    resp = await client.post(
        "/compare",
        json={"baseline_run_ids": ["a"], "candidate_run_ids": ["b"], "metric": "score"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "insufficient_data"


async def test_compare_accuracy_delta(client: AsyncClient) -> None:
    """``POST /compare`` reports a CI and significance for an accuracy delta."""
    baseline_ids = [await _seed_run(success=True) for _ in range(6)]
    # Candidate group regresses: 2 of 6 now fail.
    candidate_ids = [await _seed_run(success=True) for _ in range(4)]
    candidate_ids += [await _seed_run(success=False) for _ in range(2)]

    resp = await client.post(
        "/compare",
        json={
            "baseline_run_ids": baseline_ids,
            "candidate_run_ids": candidate_ids,
            "metric": "accuracy",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_baseline"] == 6
    assert body["n_candidate"] == 6
    assert body["baseline_mean"] == 1.0
    assert body["candidate_mean"] < 1.0
    assert body["delta"] < 0
    assert body["p_value"] is not None
    assert body["warning"] == "small_sample_ci_may_be_unreliable"


async def test_golden_crud(client: AsyncClient, monkeypatch, tmp_path) -> None:
    """``/golden`` supports create, list-with-stats, patch, and delete."""
    monkeypatch.chdir(tmp_path)  # isolate the JSONL file to the temp dir
    assert (await client.get("/golden")).json()["stats"]["n_cases"] == 0

    body = {
        "span": {"run_id": "x", "agent_name": "a"},
        "human_label": True,
        "human_notes": "ok",
        "difficulty": "easy",
    }
    created = (await client.post("/golden", json=body)).json()
    golden_id = created["id"]
    listed = (await client.get("/golden")).json()
    assert listed["stats"]["n_cases"] == 1
    assert listed["stats"]["pass_rate"] == 1.0

    patched = await client.patch(f"/golden/{golden_id}", json={"difficulty": "hard"})
    assert patched.json()["difficulty"] == "hard"

    assert (await client.delete(f"/golden/{golden_id}")).json() == {"deleted": golden_id}
    assert (await client.get("/golden")).json()["stats"]["n_cases"] == 0


async def test_golden_patch_missing_404(client: AsyncClient, monkeypatch, tmp_path) -> None:
    """Patching an unknown golden id returns the standard 404 envelope."""
    monkeypatch.chdir(tmp_path)
    resp = await client.patch("/golden/nope", json={"difficulty": "hard"})
    assert resp.status_code == 404
    assert resp.json()["error"] == "golden_not_found"


async def test_review_flow(client: AsyncClient, monkeypatch, tmp_path) -> None:
    """A flagged run appears in the queue, then a review promotes it to golden."""
    monkeypatch.chdir(tmp_path)
    run_id = await _seed_run()
    async with get_session() as session:
        session.add(
            ReviewQueueItem(
                run_id=run_id, reason="low_confidence", judge_score=0.5, judge_confidence=0.4
            )
        )
        await session.commit()

    queue = (await client.get("/review/queue")).json()
    assert len(queue["cases"]) == 1
    assert queue["cases"][0]["item"]["run_id"] == run_id

    submitted = await client.post(f"/review/{run_id}", json={"label": True, "notes": "good"})
    assert submitted.status_code == 200
    assert submitted.json()["human_label"] is True

    # The item is now reviewed (queue empty) and the golden dataset grew by one.
    assert (await client.get("/review/queue")).json()["cases"] == []
    assert (await client.get("/golden")).json()["stats"]["n_cases"] == 1


async def test_review_missing_run_404(client: AsyncClient, monkeypatch, tmp_path) -> None:
    """Reviewing an unknown run returns the standard 404 envelope."""
    monkeypatch.chdir(tmp_path)
    resp = await client.post("/review/nope", json={"label": True, "notes": "n"})
    assert resp.status_code == 404
    assert resp.json()["error"] == "run_not_found"


async def test_auth_required_when_key_set(tmp_path, monkeypatch) -> None:
    """With ``FAILPROBE_API_KEY`` set, non-health routes require the header."""
    db_file = tmp_path / "auth.db"
    monkeypatch.setenv("FAILPROBE_DB_URL", f"sqlite+aiosqlite:///{db_file.as_posix()}")
    monkeypatch.setenv("FAILPROBE_API_KEY", "secret")
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_session_factory", None)
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # Health is exempt.
        assert (await c.get("/health")).status_code == 200
        # Missing key is rejected.
        assert (await c.get("/runs")).status_code == 401
        # Correct key passes through.
        ok = await c.get("/runs", headers={"X-API-Key": "secret"})
        assert ok.status_code == 200
