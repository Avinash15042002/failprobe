"""Add the review_queue table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-04

Adds the ``review_queue`` table backing :class:`ReviewQueueItem` — runs flagged
by low-confidence judging for human review (TASK 13). Column types mirror
``failprobe/storage/models.py`` exactly.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the review_queue table."""
    op.create_table(
        "review_queue",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("judge_score", sa.Float(), nullable=False),
        sa.Column("judge_confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop the review_queue table."""
    op.drop_table("review_queue")
