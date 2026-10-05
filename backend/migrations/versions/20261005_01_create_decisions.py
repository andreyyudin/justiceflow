"""Create auditable human decisions.

Revision ID: 20261005_01
Revises:
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261005_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reviewer", sa.String(length=100), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_decisions_case_id"),
        "decisions",
        ["case_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_decisions_case_id"), table_name="decisions")
    op.drop_table("decisions")
