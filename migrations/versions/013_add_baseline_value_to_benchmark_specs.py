"""add baseline_value column to benchmark_specs

Revision ID: 013
Revises: 012
Create Date: 2026-04-22
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "benchmark_specs",
        sa.Column("baseline_value", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("benchmark_specs", "baseline_value")
