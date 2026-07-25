"""Création des métadonnées de contributions vocales consenties."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260724_0003"
down_revision: str | None = "20260724_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contributions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("anon_id", sa.Text(), nullable=False),
        sa.Column("consent_id", sa.Uuid(), nullable=False),
        sa.Column("expected_number", sa.BigInteger(), nullable=False),
        sa.Column("expected_prompt", sa.Text(), nullable=False),
        sa.Column("audio_ref", sa.Text(), nullable=True),
        sa.Column("speaker_key", sa.Text(), nullable=False),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("device_info", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column("grammar_version", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'validated', 'rejected', 'withdrawn')",
            name="ck_contributions_status",
        ),
        sa.ForeignKeyConstraint(["consent_id"], ["consents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_contrib_speaker",
        "contributions",
        ["speaker_key"],
        unique=False,
    )
    op.create_index(
        "idx_contrib_status",
        "contributions",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_contrib_status", table_name="contributions")
    op.drop_index("idx_contrib_speaker", table_name="contributions")
    op.drop_table("contributions")
