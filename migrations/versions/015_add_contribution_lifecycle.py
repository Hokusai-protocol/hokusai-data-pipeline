"""add contribution lifecycle table

Revision ID: 015
Revises: 014
Create Date: 2026-06-04
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "contribution_lifecycle",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("submission_id", sa.String(length=255), nullable=False),
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column("accepted_row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("training_run_id", sa.String(length=255), nullable=True),
        sa.Column("evaluation_run_id", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "state IN "
            "('received', 'queued', 'processing', 'processed', 'rejected', "
            "'included_in_training', 'excluded')",
            name="ck_contribution_lifecycle_state",
        ),
        sa.UniqueConstraint("submission_id", name="uq_contribution_lifecycle_submission_id"),
    )
    op.create_index(
        "ix_contribution_lifecycle_submission_id",
        "contribution_lifecycle",
        ["submission_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_contribution_lifecycle_submission_id", table_name="contribution_lifecycle")
    op.drop_table("contribution_lifecycle")
