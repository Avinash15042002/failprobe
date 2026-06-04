"""Golden-dataset CRUD routes (TASK 13).

Manages ``GoldenCase`` records — human-labelled spans used as ground truth for
meta-evaluation. The dataset is a JSONL file owned by
:class:`~failprobe.evaluator.GoldenDatasetManager`; these routes are a thin HTTP
layer over it and hold no serialization logic of their own.
"""

import dataclasses

from fastapi import APIRouter, HTTPException

from failprobe.evaluator import GoldenDatasetManager
from api.schemas import (
    GoldenCaseCreate,
    GoldenCasePatch,
    GoldenCaseSchema,
    GoldenListResponse,
    GoldenStatsSchema,
)

router = APIRouter(tags=["golden"])


def _not_found(golden_id: str) -> HTTPException:
    """Build the standard 404 for an unknown golden case id."""
    return HTTPException(
        status_code=404,
        detail={"error": "golden_not_found", "message": f"No golden case with id {golden_id}"},
    )


@router.get("/golden", response_model=GoldenListResponse)
async def list_golden() -> GoldenListResponse:
    """Return all golden cases together with dataset statistics."""
    manager = GoldenDatasetManager()
    return GoldenListResponse(
        cases=[GoldenCaseSchema.from_case(case) for case in manager.cases],
        stats=GoldenStatsSchema(**manager.get_stats()),
    )


@router.post("/golden", response_model=GoldenCaseSchema)
async def create_golden(body: GoldenCaseCreate) -> GoldenCaseSchema:
    """Create a golden case and append it to the dataset."""
    manager = GoldenDatasetManager()
    case = body.to_case()
    manager.add_case(case)
    return GoldenCaseSchema.from_case(case)


@router.patch("/golden/{golden_id}", response_model=GoldenCaseSchema)
async def update_golden(golden_id: str, body: GoldenCasePatch) -> GoldenCaseSchema:
    """Apply partial updates to a golden case's label/notes/difficulty/reviewer."""
    manager = GoldenDatasetManager()
    changes = {key: value for key, value in body.model_dump().items() if value is not None}
    for index, case in enumerate(manager.cases):
        if case.id == golden_id:
            updated = dataclasses.replace(case, **changes)
            manager.cases[index] = updated
            manager.save(manager.cases, manager.path)
            return GoldenCaseSchema.from_case(updated)
    raise _not_found(golden_id)


@router.delete("/golden/{golden_id}")
async def delete_golden(golden_id: str) -> dict:
    """Remove a golden case from the dataset."""
    manager = GoldenDatasetManager()
    remaining = [case for case in manager.cases if case.id != golden_id]
    if len(remaining) == len(manager.cases):
        raise _not_found(golden_id)
    manager.save(remaining, manager.path)
    return {"deleted": golden_id}
