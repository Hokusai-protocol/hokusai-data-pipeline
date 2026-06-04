"""add lifecycle callback tracking columns

Revision ID: 016
Revises: 015
Create Date: 2026-06-04
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contribution_lifecycle",
        sa.Column("callback_status", sa.Text(), nullable=True),
    )
    op.add_column(
        "contribution_lifecycle",
        sa.Column("callback_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "contribution_lifecycle",
        sa.Column("callback_last_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "contribution_lifecycle",
        sa.Column("callback_last_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contribution_lifecycle", "callback_last_attempt_at")
    op.drop_column("contribution_lifecycle", "callback_last_error")
    op.drop_column("contribution_lifecycle", "callback_attempts")
    op.drop_column("contribution_lifecycle", "callback_status")
