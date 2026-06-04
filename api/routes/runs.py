"""Routes for inspecting recorded agent runs.

``GET /runs`` lists runs with filtering and pagination; ``GET /runs/{run_id}``
returns a single run with its tool calls and (if any) its evaluation. All
queries use async SQLAlchemy ``select()`` statements against the shared session.
"""

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from failprobe.storage import get_session
from failprobe.storage.models import EvalResult, Run, ToolCallRecord
from api.schemas import (
    EvalResultSchema,
    RunDetailResponse,
    RunListResponse,
    RunSchema,
    ToolCallSchema,
)

router = APIRouter(tags=["runs"])


@router.get("/runs", response_model=RunListResponse)
async def list_runs(
    agent_name: Optional[str] = Query(default=None),
    success: Optional[bool] = Query(default=None),
    failure_type: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    order: Literal["asc", "desc"] = Query(default="desc"),
) -> RunListResponse:
    """List recorded runs, newest first by default, with optional filters."""
    filters = []
    if agent_name is not None:
        filters.append(Run.agent_name == agent_name)
    if success is not None:
        filters.append(Run.success == success)
    if failure_type is not None:
        filters.append(Run.failure_type == failure_type)

    ordering = Run.created_at.asc() if order == "asc" else Run.created_at.desc()

    async with get_session() as session:
        total = (
            await session.execute(select(func.count()).select_from(Run).where(*filters))
        ).scalar_one()
        rows = (
            await session.execute(
                select(Run).where(*filters).order_by(ordering).limit(limit).offset(offset)
            )
        ).scalars().all()

    return RunListResponse(total=total, runs=[RunSchema.from_orm_row(r) for r in rows])


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
async def get_run(run_id: str) -> RunDetailResponse:
    """Return a single run with its tool calls and evaluation, or 404."""
    async with get_session() as session:
        run = (
            await session.execute(select(Run).where(Run.id == run_id))
        ).scalar_one_or_none()
        if run is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "run_not_found", "message": f"No run with id {run_id}"},
            )
        tool_calls = (
            await session.execute(
                select(ToolCallRecord)
                .where(ToolCallRecord.run_id == run_id)
                .order_by(ToolCallRecord.timestamp.asc())
            )
        ).scalars().all()
        eval_row = (
            await session.execute(select(EvalResult).where(EvalResult.run_id == run_id))
        ).scalars().first()

    return RunDetailResponse(
        run=RunSchema.from_orm_row(run),
        tool_calls=[ToolCallSchema.from_record(tc) for tc in tool_calls],
        eval_result=EvalResultSchema.from_orm_row(eval_row) if eval_row is not None else None,
    )
