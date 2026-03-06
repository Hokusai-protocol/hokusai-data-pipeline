"""add evaluation_schedules table

Revision ID: 011
Revises: 010
Create Date: 2026-03-06
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", sa.String(length=255), nullable=False),
        sa.Column("cron_expression", sa.String(length=255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", name="uq_evaluation_schedules_model_id"),
    )
    op.create_index("ix_evaluation_schedules_model_id", "evaluation_schedules", ["model_id"])


def downgrade() -> None:
    op.drop_index("ix_evaluation_schedules_model_id", table_name="evaluation_schedules")
    op.drop_table("evaluation_schedules")
