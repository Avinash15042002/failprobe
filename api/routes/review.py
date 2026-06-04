"""Human-review queue routes (TASK 13).

``GET /review/queue`` lists unreviewed runs (flagged by low-confidence judging)
joined with their originating run. ``POST /review/{run_id}`` records a human
label: it promotes the run into the golden dataset and marks its queue item(s)
reviewed.
"""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from failprobe.evaluator import GoldenDatasetManager
from failprobe.models import GoldenCase
from failprobe.storage import get_session
from failprobe.storage.models import ReviewQueueItem, Run, ToolCallRecord
from api.routes._common import span_from_run
from api.schemas import (
    GoldenCaseSchema,
    ReviewQueueEntrySchema,
    ReviewQueueItemSchema,
    ReviewQueueResponse,
    ReviewRequest,
    RunSchema,
)

router = APIRouter(tags=["review"])

# Human reviews submitted through the queue carry these defaults; the
# ReviewRequest body only supplies a pass/fail label and free-text notes.
_DEFAULT_DIFFICULTY = "medium"
_REVIEWED_BY = "human-review"


@router.get("/review/queue", response_model=ReviewQueueResponse)
async def review_queue() -> ReviewQueueResponse:
    """List unreviewed review-queue items joined with their runs."""
    async with get_session() as session:
        rows = (
            await session.execute(
                select(ReviewQueueItem, Run)
                .join(Run, ReviewQueueItem.run_id == Run.id)
                .where(ReviewQueueItem.reviewed.is_(False))
                .order_by(ReviewQueueItem.created_at.desc())
            )
        ).all()

    entries = [
        ReviewQueueEntrySchema(
            item=ReviewQueueItemSchema.model_validate(item),
            run=RunSchema.from_orm_row(run),
        )
        for item, run in rows
    ]
    return ReviewQueueResponse(cases=entries)


@router.post("/review/{run_id}", response_model=GoldenCaseSchema)
async def submit_review(run_id: str, request: ReviewRequest) -> GoldenCaseSchema:
    """Record a human label: promote the run to the golden dataset, mark reviewed.

    Reconstructs the run's span, builds a :class:`GoldenCase` from the human's
    pass/fail label and notes, appends it to the golden dataset, and flips any
    pending review-queue items for the run to ``reviewed=True``.
    """
    async with get_session() as session:
        run = (
            await session.execute(select(Run).where(Run.id == run_id))
        ).scalar_one_or_none()
        if run is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "run_not_found", "message": f"No run with id {run_id}"},
            )
        tool_rows = list(
            (
                await session.execute(
                    select(ToolCallRecord).where(ToolCallRecord.run_id == run_id)
                )
            ).scalars()
        )
        pending = (
            await session.execute(
                select(ReviewQueueItem)
                .where(ReviewQueueItem.run_id == run_id)
                .where(ReviewQueueItem.reviewed.is_(False))
            )
        ).scalars()
        for item in pending:
            item.reviewed = True
        await session.commit()

    case = GoldenCase(
        id=str(uuid4()),
        span=span_from_run(run, tool_rows),
        human_label=request.label,
        human_notes=request.notes,
        difficulty=_DEFAULT_DIFFICULTY,
        created_at=datetime.now(timezone.utc),
        reviewed_by=_REVIEWED_BY,
    )
    GoldenDatasetManager().add_case(case)
    return GoldenCaseSchema.from_case(case)
