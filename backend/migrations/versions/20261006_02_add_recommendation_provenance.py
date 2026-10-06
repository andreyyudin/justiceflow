"""Add immutable recommendation provenance.

Revision ID: 20261006_02
Revises: 20261005_01
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_02"
down_revision: str | None = "20261005_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recommendations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("recommendation", sa.String(length=16), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("model_confidence", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "recommendation IN ('urgent', 'high', 'standard')",
            name="ck_recommendations_priority",
        ),
        sa.CheckConstraint(
            "model_confidence >= 0 AND model_confidence <= 1",
            name="ck_recommendations_confidence",
        ),
        sa.CheckConstraint(
            "latency_ms >= 0",
            name="ck_recommendations_latency",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recommendations_case_id"),
        "recommendations",
        ["case_id"],
        unique=False,
    )

    op.add_column(
        "decisions",
        sa.Column("recommendation_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "decisions",
        sa.Column(
            "decision_type",
            sa.String(length=16),
            server_default=sa.text("'legacy'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_decisions_type",
        "decisions",
        "decision_type IN ('accepted', 'overridden', 'legacy')",
    )
    op.create_foreign_key(
        "fk_decisions_recommendation_id",
        "decisions",
        "recommendations",
        ["recommendation_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        op.f("ix_decisions_recommendation_id"),
        "decisions",
        ["recommendation_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_decisions_recommendation_id"),
        table_name="decisions",
    )
    op.drop_constraint(
        "fk_decisions_recommendation_id",
        "decisions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_decisions_type",
        "decisions",
        type_="check",
    )
    op.drop_column("decisions", "decision_type")
    op.drop_column("decisions", "recommendation_id")

    op.drop_index(
        op.f("ix_recommendations_case_id"),
        table_name="recommendations",
    )
    op.drop_table("recommendations")
