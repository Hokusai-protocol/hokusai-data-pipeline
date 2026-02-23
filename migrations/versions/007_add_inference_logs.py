"""add inference logs table

Revision ID: 007
Revises: 003
Create Date: 2026-02-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "007"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "inference_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("api_token_id", sa.String(length=255), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("model_version", sa.String(length=255), nullable=False),
        sa.Column("input_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("trace_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("outcome_score", sa.Float(), nullable=True),
        sa.Column("outcome_type", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("outcome_recorded_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_inference_logs_api_token_id", "inference_logs", ["api_token_id"])
    op.create_index(
        "ix_inference_logs_model_name_model_version",
        "inference_logs",
        ["model_name", "model_version"],
    )
    op.create_index("ix_inference_logs_created_at", "inference_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_inference_logs_created_at", table_name="inference_logs")
    op.drop_index("ix_inference_logs_model_name_model_version", table_name="inference_logs")
    op.drop_index("ix_inference_logs_api_token_id", table_name="inference_logs")
    op.drop_table("inference_logs")
