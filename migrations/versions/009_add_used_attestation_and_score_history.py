"""add used attestations and score transition history

Revision ID: 009
Revises: 008
Create Date: 2026-02-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "used_attestations",
        sa.Column("attestation_hash", sa.String(length=64), nullable=False),
        sa.Column("mint_audit_ref", sa.String(length=255), nullable=False),
        sa.Column("model_id", sa.String(length=255), nullable=False),
        sa.Column("attestation_nonce", sa.String(length=128), nullable=True),
        sa.Column("decision_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("attestation_hash"),
        sa.UniqueConstraint("attestation_nonce", name="uq_used_attestations_nonce"),
    )
    op.create_index("ix_used_attestations_model_id", "used_attestations", ["model_id"])
    op.create_index("ix_used_attestations_consumed_at", "used_attestations", ["consumed_at"])

    op.create_table(
        "score_transitions",
        sa.Column("transition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", sa.String(length=255), nullable=False),
        sa.Column("attestation_hash", sa.String(length=64), nullable=False),
        sa.Column("baseline_run_id", sa.String(length=255), nullable=False),
        sa.Column("run_id", sa.String(length=255), nullable=False),
        sa.Column("from_score", sa.Float(), nullable=False),
        sa.Column("to_score", sa.Float(), nullable=False),
        sa.Column("delta_percentage_points", sa.Float(), nullable=False),
        sa.Column("reason", sa.String(length=128), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["attestation_hash"],
            ["used_attestations.attestation_hash"],
            name="fk_score_transitions_attestation_hash",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("transition_id"),
    )
    op.create_index("ix_score_transitions_model_id", "score_transitions", ["model_id"])
    op.create_index("ix_score_transitions_recorded_at", "score_transitions", ["recorded_at"])


def downgrade() -> None:
    op.drop_index("ix_score_transitions_recorded_at", table_name="score_transitions")
    op.drop_index("ix_score_transitions_model_id", table_name="score_transitions")
    op.drop_table("score_transitions")

    op.drop_index("ix_used_attestations_consumed_at", table_name="used_attestations")
    op.drop_index("ix_used_attestations_model_id", table_name="used_attestations")
    op.drop_table("used_attestations")
