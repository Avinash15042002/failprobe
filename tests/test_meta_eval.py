"""Tests for the evaluator's LLM-as-Judge (``failprobe/evaluator/judge.py``).

Real API calls are never made: every test monkeypatches the private ``_call_llm``
network seam to return canned text. The judge's never-raise contract, JSON
parse/retry logic, timeout handling, and ``EvalResult`` persistence are all
exercised against that seam.
"""

import asyncio
import random
from datetime import datetime, timezone

import numpy as np
import pytest
from sqlalchemy import func, select

from failprobe.config import ProbeConfig, configure, get_config
from failprobe.evaluator import judge_run, should_flag_for_review
from failprobe.evaluator import meta_eval as meta_eval_mod
from failprobe.evaluator.golden_dataset import GoldenDatasetManager
from failprobe.evaluator.judge import JudgeResult
from failprobe.evaluator import judge as judge_mod
from failprobe.evaluator.meta_eval import run_meta_eval
from failprobe.models import GoldenCase
from failprobe.storage import db
from failprobe.storage.db import get_session, init_db
from failprobe.storage.models import EvalResult

from conftest import make_span, make_tool_call

_RUBRIC = "Score the run."
_VALID_JSON = '{"score": 0.9, "reasoning": "looks good", "confidence": 0.8, "key_issues": []}'

# Captured before any monkeypatching so the persistence test can restore the real helper.
_REAL_WRITE_EVAL = judge_mod._write_eval_result


@pytest.fixture(autouse=True)
def _no_persist(monkeypatch) -> None:
    """Stub out DB persistence by default so judge tests need no database.

    Tests that specifically verify persistence undo this with their own fresh
    DB and the real ``_write_eval_result``.
    """

    async def _noop(_result: JudgeResult) -> None:
        return None

    monkeypatch.setattr(judge_mod, "_write_eval_result", _noop)


@pytest.fixture(autouse=True)
def _restore_config() -> None:
    """Restore the default ProbeConfig after tests that mutate it."""
    yield
    configure(ProbeConfig())


def _fake_llm(*returns: str):
    """Build a fake ``_call_llm`` returning ``returns`` in order, recording prompts."""
    calls: list[str] = []
    sequence = iter(returns)

    async def _call(prompt: str, model: str) -> str:
        calls.append(prompt)
        return next(sequence)

    _call.prompts = calls  # type: ignore[attr-defined]
    return _call


async def test_judge_parse_failure(monkeypatch) -> None:
    """Two unparseable responses yield score=0.0, confidence=0.0, parse_error."""
    monkeypatch.setattr(judge_mod, "_call_llm", _fake_llm("not json", "still not json"))

    result = await judge_run(make_span(run_id="r1"), _RUBRIC, model="claude-haiku-4")

    assert isinstance(result, JudgeResult)
    assert result.run_id == "r1"
    assert result.score == 0.0
    assert result.confidence == 0.0
    assert result.reasoning == "parse_error"
    assert result.model_used == "claude-haiku-4"


async def test_judge_retry(monkeypatch) -> None:
    """A first parse failure retries once with the stricter prompt, then succeeds."""
    fake = _fake_llm("garbage, not json", _VALID_JSON)
    monkeypatch.setattr(judge_mod, "_call_llm", fake)

    result = await judge_run(make_span(run_id="r2"), _RUBRIC, model="claude-haiku-4")

    assert len(fake.prompts) == 2
    assert "Return only raw JSON, no backticks." not in fake.prompts[0]
    assert fake.prompts[1].endswith("Return only raw JSON, no backticks.")
    assert result.score == 0.9
    assert result.confidence == 0.8
    assert result.reasoning == "looks good"


async def test_judge_happy_path(monkeypatch) -> None:
    """A single valid JSON response is parsed without any retry."""
    fake = _fake_llm(_VALID_JSON)
    monkeypatch.setattr(judge_mod, "_call_llm", fake)

    result = await judge_run(make_span(run_id="r3"), _RUBRIC)

    assert len(fake.prompts) == 1
    assert result.score == 0.9
    assert result.reasoning == "looks good"


async def test_judge_never_raises_on_llm_error(monkeypatch) -> None:
    """An exception from the LLM seam is swallowed into a judge_error result."""

    async def _boom(prompt: str, model: str) -> str:
        raise RuntimeError("network down")

    monkeypatch.setattr(judge_mod, "_call_llm", _boom)

    result = await judge_run(make_span(run_id="r4"), _RUBRIC)

    assert result.score == 0.0
    assert result.confidence == 0.0
    assert result.reasoning == "judge_error"


async def test_judge_respects_timeout(monkeypatch) -> None:
    """A call slower than ``judge_timeout`` is cancelled and returns judge_error."""
    configure(ProbeConfig(judge_timeout=0.01))
    assert get_config().judge_timeout == 0.01

    async def _slow(prompt: str, model: str) -> str:
        await asyncio.sleep(1.0)
        return _VALID_JSON

    monkeypatch.setattr(judge_mod, "_call_llm", _slow)

    result = await judge_run(make_span(run_id="r5"), _RUBRIC)

    assert result.reasoning == "judge_error"
    assert result.score == 0.0


async def test_judge_handles_openai_prefix(monkeypatch) -> None:
    """A ``gpt`` model string is accepted and judged like any other model."""
    monkeypatch.setattr(judge_mod, "_call_llm", _fake_llm(_VALID_JSON))

    result = await judge_run(make_span(run_id="r6"), _RUBRIC, model="gpt-4o-mini")

    assert result.model_used == "gpt-4o-mini"
    assert result.score == 0.9


async def test_judge_persists_eval_result(monkeypatch, tmp_path) -> None:
    """Every judge call is written to the ``EvalResult`` table."""
    db_file = tmp_path / "judge.db"
    monkeypatch.setenv("FAILPROBE_DB_URL", f"sqlite+aiosqlite:///{db_file.as_posix()}")
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_session_factory", None)
    # Restore the real persistence helper (the autouse fixture stubbed it out).
    monkeypatch.setattr(judge_mod, "_write_eval_result", _REAL_WRITE_EVAL)
    monkeypatch.setattr(judge_mod, "_call_llm", _fake_llm(_VALID_JSON))
    await init_db()

    span = make_span(run_id="r7", tool_calls=[make_tool_call("search", {"q": "x"})])
    result = await judge_run(span, _RUBRIC, model="claude-haiku-4")

    async with get_session() as session:
        count = (await session.execute(select(func.count()).select_from(EvalResult))).scalar_one()
        row = (await session.execute(select(EvalResult))).scalar_one()
    assert count == 1
    assert row.run_id == "r7"
    assert row.score == result.score
    assert row.judge_model == "claude-haiku-4"


# ---------------------------------------------------------------------------
# Meta-evaluation (TASK 13)
#
# These tests never call a real judge: ``meta_eval.judge_run`` is monkeypatched
# with a deterministic fake whose score is looked up per run id. Bootstrap
# randomness is seeded so CI assertions are reproducible.
# ---------------------------------------------------------------------------

_MODEL = "claude-haiku-4"


def _golden_case(idx: int, label: bool) -> GoldenCase:
    """Build a golden case whose span run id encodes its index."""
    return GoldenCase(
        id=f"c{idx}",
        span=make_span(run_id=f"c{idx}"),
        human_label=label,
        human_notes="",
        difficulty="easy",
        created_at=datetime.now(timezone.utc),
        reviewed_by="tester",
    )


def _fake_judge(score_by_run: dict[str, float]):
    """Build a fake ``judge_run`` returning the mapped score for each span."""

    async def _judge(span, rubric, model: str = _MODEL) -> JudgeResult:
        return JudgeResult(
            run_id=span.run_id,
            score=score_by_run[span.run_id],
            reasoning="",
            model_used=model,
            latency_ms=0.0,
            confidence=1.0,
        )

    return _judge


def _scores_for(cases: list[GoldenCase], correct: list[bool]) -> dict[str, float]:
    """Map each case to a judge score that is correct/incorrect as specified.

    A correct prediction scores on the right side of the 0.5 threshold for the
    case's human label; an incorrect one scores on the wrong side.
    """
    scores: dict[str, float] = {}
    for case, is_correct in zip(cases, correct):
        right_side = 1.0 if case.human_label else 0.0
        wrong_side = 0.0 if case.human_label else 1.0
        scores[case.span.run_id] = right_side if is_correct else wrong_side
    return scores


async def test_meta_eval_perfect_judge(monkeypatch) -> None:
    """A judge that always agrees with humans → accuracy 1.0, CI (1.0, 1.0)."""
    cases = [_golden_case(i, label=(i % 2 == 0)) for i in range(30)]
    monkeypatch.setattr(meta_eval_mod, "judge_run", _fake_judge(_scores_for(cases, [True] * 30)))
    np.random.seed(0)

    report = await run_meta_eval(cases, judge_model=_MODEL)

    assert report.judge_accuracy == 1.0
    assert report.n_correct == 30
    assert report.confidence_interval == (1.0, 1.0)
    assert report.precision == 1.0
    assert report.recall == 1.0
    assert report.f1 == 1.0
    assert report.disagreement_rate == 0.0
    assert report.warning is None


async def test_meta_eval_random_judge(monkeypatch) -> None:
    """A chance-level judge → accuracy ≈ 0.5 with a CI that contains 0.5."""
    cases = [_golden_case(i, label=(i % 2 == 0)) for i in range(200)]
    rng = random.Random(42)
    correct = [rng.random() < 0.5 for _ in cases]
    monkeypatch.setattr(meta_eval_mod, "judge_run", _fake_judge(_scores_for(cases, correct)))
    np.random.seed(42)

    report = await run_meta_eval(cases, judge_model=_MODEL)

    assert abs(report.judge_accuracy - 0.5) < 0.12
    lower, upper = report.confidence_interval
    assert lower <= 0.5 <= upper


async def test_meta_eval_too_few_cases_warning(monkeypatch) -> None:
    """Fewer than 10 cases fires ``too_few_cases`` and skips the bootstrap CI."""
    cases = [_golden_case(i, label=True) for i in range(5)]
    monkeypatch.setattr(meta_eval_mod, "judge_run", _fake_judge(_scores_for(cases, [True] * 5)))

    report = await run_meta_eval(cases, judge_model=_MODEL)

    assert report.warning == "too_few_cases"
    assert report.n_cases == 5
    # CI is degenerate (point estimate repeated) because it was skipped.
    assert report.confidence_interval == (report.judge_accuracy, report.judge_accuracy)


async def test_meta_eval_ci_narrows_with_more_cases(monkeypatch) -> None:
    """More cases at the same accuracy yield a narrower bootstrap CI."""

    async def _ci_width(n: int) -> float:
        cases = [_golden_case(i, label=(i % 2 == 0)) for i in range(n)]
        # Deterministic ~70% accuracy independent of n.
        correct = [(i % 10) < 7 for i in range(n)]
        monkeypatch.setattr(meta_eval_mod, "judge_run", _fake_judge(_scores_for(cases, correct)))
        np.random.seed(7)
        report = await run_meta_eval(cases, judge_model=_MODEL)
        lower, upper = report.confidence_interval
        return upper - lower

    width_small = await _ci_width(20)
    width_large = await _ci_width(100)

    assert width_large < width_small


def test_should_flag_for_review_low_confidence() -> None:
    """``should_flag_for_review`` fires on low confidence or an ambiguous score."""
    low_conf = JudgeResult("r", score=0.9, reasoning="", model_used=_MODEL, latency_ms=0.0,
                           confidence=0.5)
    ambiguous = JudgeResult("r", score=0.5, reasoning="", model_used=_MODEL, latency_ms=0.0,
                            confidence=0.95)
    decisive = JudgeResult("r", score=0.95, reasoning="", model_used=_MODEL, latency_ms=0.0,
                           confidence=0.9)

    assert should_flag_for_review(low_conf) is True
    assert should_flag_for_review(ambiguous) is True
    assert should_flag_for_review(decisive) is False


def test_golden_dataset_roundtrips(tmp_path) -> None:
    """``save`` then ``load`` returns an identical list of cases (no data loss)."""
    path = str(tmp_path / "golden.jsonl")
    cases = [
        GoldenCase(
            id="g1",
            span=make_span(run_id="g1", tool_calls=[make_tool_call("search", {"q": "x"})]),
            human_label=True,
            human_notes="clearly correct",
            difficulty="easy",
            created_at=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
            reviewed_by="alice",
        ),
        GoldenCase(
            id="g2",
            span=make_span(run_id="g2"),
            human_label=False,
            human_notes="wrong city",
            difficulty="hard",
            created_at=datetime(2026, 6, 4, 12, 5, tzinfo=timezone.utc),
            reviewed_by="bob",
        ),
    ]

    GoldenDatasetManager().save(cases, path)
    loaded = GoldenDatasetManager().load(path)

    assert loaded == cases


def test_golden_dataset_stats(tmp_path) -> None:
    """``get_stats`` reports counts, pass rate, and difficulty distribution."""
    path = str(tmp_path / "golden.jsonl")
    cases = [
        _golden_case(0, label=True),
        _golden_case(1, label=True),
        _golden_case(2, label=False),
    ]
    cases[2].difficulty = "hard"
    manager = GoldenDatasetManager()
    manager.save(cases, path)

    stats = manager.get_stats()

    assert stats["n_cases"] == 3
    assert stats["pass_rate"] == pytest.approx(2 / 3)
    assert stats["difficulty_distribution"] == {"easy": 2, "hard": 1}
    assert stats["last_updated"] is not None
