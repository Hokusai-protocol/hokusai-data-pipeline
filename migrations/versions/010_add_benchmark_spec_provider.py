"""add provider enum column to benchmark_specs

Revision ID: 010
Revises: 009
Create Date: 2026-03-05
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None

benchmark_provider_enum = sa.Enum("hokusai", "kaggle", name="benchmark_provider")


def upgrade() -> None:
    benchmark_provider_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "benchmark_specs",
        sa.Column(
            "provider",
            benchmark_provider_enum,
            nullable=False,
            server_default="hokusai",
        ),
    )


def downgrade() -> None:
    op.drop_column("benchmark_specs", "provider")
    benchmark_provider_enum.drop(op.get_bind(), checkfirst=True)
