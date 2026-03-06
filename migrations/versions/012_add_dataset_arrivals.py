"""add dataset_arrivals table

Revision ID: 012
Revises: 011
Create Date: 2026-03-06
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dataset_arrivals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bucket", sa.String(length=255), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("object_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("etag", sa.String(length=255), nullable=True),
        sa.Column("model_id", sa.String(length=255), nullable=True),
        sa.Column("dataset_version", sa.String(length=255), nullable=True),
        sa.Column("spec_id", sa.String(length=255), nullable=True),
        sa.Column("reeval_triggered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("s3_event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dataset_arrivals_model_id", "dataset_arrivals", ["model_id"])


def downgrade() -> None:
    op.drop_index("ix_dataset_arrivals_model_id", table_name="dataset_arrivals")
    op.drop_table("dataset_arrivals")
