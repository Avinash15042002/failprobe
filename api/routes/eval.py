"""Evaluation routes (TASK 13): real LLM judging and meta-evaluation.

``POST /eval/run`` reconstructs the stored run as an :class:`AgentSpan`, judges
it via :func:`judge_run`, queues the run for human review if the judge is
low-confidence, and returns the persisted :class:`EvalResult`.
``GET /eval/judge-accuracy`` scores the judge against the golden dataset and
returns a :class:`MetaEvalReport`, or signals that no golden dataset exists yet.

This module is a thin HTTP layer: all judging/meta-eval logic lives in
``agentprobe.evaluator``.
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from agentprobe.config import get_config
from agentprobe.evaluator import (
    GoldenDatasetManager,
    default_rubric,
    judge_run,
    run_meta_eval,
    should_flag_for_review,
)
from agentprobe.storage import get_session
from agentprobe.storage.models import EvalResult, ReviewQueueItem, Run, ToolCallRecord
from api.routes._common import span_from_run
from api.schemas import EvalResultSchema, EvalRunRequest, MetaEvalReportSchema

router = APIRouter(tags=["eval"])

# Why a low-confidence run was queued for review (stored on the queue item).
_FLAG_REASON = "low_confidence"


@router.post("/eval/run", response_model=EvalResultSchema)
async def run_eval(request: EvalRunRequest) -> EvalResultSchema:
    """Judge a stored run with the LLM judge and persist the evaluation.

    Reconstructs the run's :class:`AgentSpan` from storage, calls the judge
    (which writes its own ``EvalResult`` row), flags the run for human review if
    confidence is low, and returns the freshly persisted evaluation.
    """
    model = request.model or get_config().judge_model

    async with get_session() as session:
        run = (
            await session.execute(select(Run).where(Run.id == request.run_id))
        ).scalar_one_or_none()
        if run is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "run_not_found", "message": f"No run with id {request.run_id}"},
            )
        tool_rows = list(
            (
                await session.execute(
                    select(ToolCallRecord).where(ToolCallRecord.run_id == request.run_id)
                )
            ).scalars()
        )

    span = span_from_run(run, tool_rows)
    judge_result = await judge_run(span, default_rubric(), model=model)

    async with get_session() as session:
        if should_flag_for_review(judge_result):
            session.add(
                ReviewQueueItem(
                    run_id=request.run_id,
                    reason=_FLAG_REASON,
                    judge_score=judge_result.score,
                    judge_confidence=judge_result.confidence,
                )
            )
            await session.commit()
        eval_row = (
            await session.execute(
                select(EvalResult)
                .where(EvalResult.run_id == request.run_id)
                .order_by(EvalResult.created_at.desc())
            )
        ).scalars().first()

    if eval_row is None:
        raise HTTPException(
            status_code=500,
            detail={"error": "eval_not_persisted", "message": "Judge result was not stored"},
        )
    return EvalResultSchema.from_orm_row(eval_row)


@router.get("/eval/judge-accuracy")
async def judge_accuracy() -> dict:
    """Score the judge against the golden dataset, or report none exists.

    Returns a :class:`MetaEvalReport` (as a dict) when golden cases are present,
    otherwise the ``no_golden_dataset`` marker.
    """
    manager = GoldenDatasetManager()
    if not manager.cases:
        return {"error": "no_golden_dataset"}
    report = await run_meta_eval(manager.cases, judge_model=get_config().judge_model)
    return MetaEvalReportSchema.from_report(report).model_dump(mode="json")
