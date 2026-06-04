"""Routes for failure analytics.

``GET /failures/taxonomy`` aggregates failed runs by failure type and joins the
counts with :data:`FAILURE_DESCRIPTIONS`. ``GET /failures`` lists the individual
failed runs with filtering and pagination. A "failure" is any run with
``success == False``; a failed run whose ``failure_type`` was never set is
bucketed under :data:`FailureType.UNKNOWN`.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from failprobe.classifier import FAILURE_DESCRIPTIONS, FailureType
from failprobe.storage import get_session
from failprobe.storage.models import Run
from api.schemas import (
    FailureBreakdownSchema,
    FailureListResponse,
    RunSchema,
    TaxonomyResponse,
)

router = APIRouter(tags=["failures"])


@router.get("/failures/taxonomy", response_model=TaxonomyResponse)
async def failure_taxonomy() -> TaxonomyResponse:
    """Aggregate failed runs by failure type across the whole dataset.

    Every one of the 15 failure types is always present in the breakdown, with
    a count of zero when it has never occurred.
    """
    async with get_session() as session:
        total_runs = (
            await session.execute(select(func.count()).select_from(Run))
        ).scalar_one()
        grouped = (
            await session.execute(
                select(Run.failure_type, func.count())
                .where(Run.success.is_(False))
                .group_by(Run.failure_type)
            )
        ).all()

    counts: dict[str, int] = {}
    for failure_type, count in grouped:
        key = failure_type or FailureType.UNKNOWN.value
        counts[key] = counts.get(key, 0) + count

    total_failures = sum(counts.values())

    breakdown: dict[str, FailureBreakdownSchema] = {}
    for ft in FailureType:
        count = counts.get(ft.value, 0)
        pct = round(count / total_failures * 100, 2) if total_failures else 0.0
        breakdown[ft.value] = FailureBreakdownSchema(
            count=count,
            description=FAILURE_DESCRIPTIONS[ft],
            pct=pct,
        )

    failure_rate = round(total_failures / total_runs, 4) if total_runs else 0.0

    return TaxonomyResponse(
        breakdown=breakdown,
        total_failures=total_failures,
        total_runs=total_runs,
        failure_rate=failure_rate,
    )


@router.get("/failures", response_model=FailureListResponse)
async def list_failures(
    agent_name: Optional[str] = Query(default=None),
    failure_type: Optional[str] = Query(default=None),
    from_date: Optional[datetime] = Query(default=None),
    to_date: Optional[datetime] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> FailureListResponse:
    """List failed runs (``success == False``) with optional filters."""
    filters = [Run.success.is_(False)]
    if agent_name is not None:
        filters.append(Run.agent_name == agent_name)
    if failure_type is not None:
        filters.append(Run.failure_type == failure_type)
    if from_date is not None:
        filters.append(Run.created_at >= from_date)
    if to_date is not None:
        filters.append(Run.created_at <= to_date)

    async with get_session() as session:
        total = (
            await session.execute(select(func.count()).select_from(Run).where(*filters))
        ).scalar_one()
        rows = (
            await session.execute(
                select(Run)
                .where(*filters)
                .order_by(Run.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()

    return FailureListResponse(total=total, failures=[RunSchema.from_orm_row(r) for r in rows])
