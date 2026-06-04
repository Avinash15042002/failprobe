"""Baseline snapshotting for the regression layer.

A *baseline* is a frozen set of aggregate metrics (accuracy, average cost,
per-case pass/fail vector, ...) captured from one suite run and stored so a
later run can be compared against it. Baselines live in the
:class:`~agentprobe.storage.models.RegressionBaseline` table; the metrics blob is
JSON-serialized into its ``metrics`` text column.

This module owns only persistence of that blob — it computes no statistics and
runs no agents. The runner (``runner.py``) builds the metrics dict and reads it
back; the statistical comparison happens in ``stats.py``.

Default baseline name is ``"main"`` (spec: "Override with ``--baseline-name``").
"""

import json
from typing import Optional

from sqlalchemy import select

from agentprobe.storage.db import get_session, init_db
from agentprobe.storage.models import RegressionBaseline

DEFAULT_BASELINE_NAME = "main"


async def save_baseline(
    name: str,
    metrics: dict,
    n_runs: int,
) -> RegressionBaseline:
    """Persist a new baseline snapshot and return the created ORM row.

    A fresh row is inserted on every call (baselines are append-only history);
    :func:`load_baseline` returns the most recent one for a given name. The
    ``metrics`` dict is JSON-serialized into the row's ``metrics`` column.

    Args:
        name: Logical baseline name (e.g. ``"main"`` or a release tag).
        metrics: Aggregate metrics to freeze. Must be JSON-serializable.
        n_runs: Number of runs/cases the metrics were computed over.

    Returns:
        The persisted :class:`RegressionBaseline` row (with ``id`` and
        ``created_at`` populated).
    """
    baseline = RegressionBaseline(
        name=name,
        metrics=json.dumps(metrics),
        n_runs=n_runs,
    )
    async with get_session() as session:
        session.add(baseline)
        await session.commit()
        await session.refresh(baseline)
    return baseline


async def load_baseline(name: str = DEFAULT_BASELINE_NAME) -> Optional[RegressionBaseline]:
    """Load the most recently saved baseline with the given name.

    Args:
        name: The baseline name to look up. Defaults to ``"main"``.

    Returns:
        The newest :class:`RegressionBaseline` row for ``name``, or ``None`` if
        no baseline has been saved under that name.
    """
    async with get_session() as session:
        result = await session.execute(
            select(RegressionBaseline)
            .where(RegressionBaseline.name == name)
            .order_by(RegressionBaseline.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def list_baselines() -> list[RegressionBaseline]:
    """Return the most recent baseline snapshot for each distinct name.

    Baselines are append-only history (:func:`save_baseline` inserts a fresh row
    on every call), so this collapses that history to one row per name — the
    newest — ordered newest-first. This is the engine behind ``probe baseline
    list`` (TASK 15). The database is initialized first so the command works as a
    standalone entry point, mirroring :func:`snapshot_baseline`.

    Returns:
        One :class:`RegressionBaseline` per distinct name, newest first.
    """
    await init_db()
    async with get_session() as session:
        result = await session.execute(
            select(RegressionBaseline).order_by(RegressionBaseline.created_at.desc())
        )
        rows = result.scalars().all()

    seen: set[str] = set()
    latest: list[RegressionBaseline] = []
    for row in rows:
        if row.name not in seen:
            seen.add(row.name)
            latest.append(row)
    return latest
