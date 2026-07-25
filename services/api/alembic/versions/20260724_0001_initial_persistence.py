"""Création initiale des tables recognitions et feedbacks."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260724_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recognitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("anon_id", sa.Text(), nullable=False),
        sa.Column("recognized_number", sa.BigInteger(), nullable=True),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("raw_asr_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column(
            "alternatives",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column("grammar_version", sa.Text(), nullable=False),
        sa.Column("latency_total_ms", sa.Integer(), nullable=True),
        sa.Column("latency_asr_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision IN ('accept', 'confirm', 'repeat')",
            name="ck_recognitions_decision",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_recognitions_anon",
        "recognitions",
        ["anon_id", sa.text("created_at DESC")],
        unique=False,
    )

    op.create_table(
        "feedbacks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recognition_id", sa.Uuid(), nullable=False),
        sa.Column("anon_id", sa.Text(), nullable=False),
        sa.Column("feedback_type", sa.Text(), nullable=False),
        sa.Column("proposed_number", sa.BigInteger(), nullable=True),
        sa.Column("corrected_number", sa.BigInteger(), nullable=True),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column("grammar_version", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "feedback_type IN " "('confirmed', 'corrected', 'rejected', 'repeat_requested')",
            name="ck_feedbacks_type",
        ),
        sa.ForeignKeyConstraint(
            ["recognition_id"],
            ["recognitions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_feedbacks_recognition",
        "feedbacks",
        ["recognition_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_feedbacks_recognition", table_name="feedbacks")
    op.drop_table("feedbacks")
    op.drop_index("idx_recognitions_anon", table_name="recognitions")
    op.drop_table("recognitions")
