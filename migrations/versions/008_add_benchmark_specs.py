"""add benchmark specs table

Revision ID: 008
Revises: 007
Create Date: 2026-02-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "benchmark_specs",
        sa.Column("spec_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", sa.String(length=255), nullable=False),
        sa.Column("dataset_id", sa.String(length=255), nullable=False),
        sa.Column("dataset_version", sa.String(length=255), nullable=False),
        sa.Column("eval_split", sa.String(length=64), nullable=False),
        sa.Column("metric_name", sa.String(length=128), nullable=False),
        sa.Column("metric_direction", sa.String(length=32), nullable=False),
        sa.Column("tiebreak_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("input_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("eval_container_digest", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("spec_id"),
        sa.UniqueConstraint(
            "model_id",
            "dataset_id",
            "dataset_version",
            name="uq_benchmark_specs_model_dataset_version",
        ),
    )
    op.create_index("ix_benchmark_specs_model_id", "benchmark_specs", ["model_id"])
    op.create_index(
        "ix_benchmark_specs_model_active",
        "benchmark_specs",
        ["model_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_benchmark_specs_model_active", table_name="benchmark_specs")
    op.drop_index("ix_benchmark_specs_model_id", table_name="benchmark_specs")
    op.drop_table("benchmark_specs")
