"""Création de la table consents (consentement versionné, story 4.1)."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260724_0002"
down_revision: str | None = "20260724_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "consents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("anon_id", sa.Text(), nullable=False),
        sa.Column("consent_version", sa.Text(), nullable=False),
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "withdrawn",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_consents_anon",
        "consents",
        ["anon_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_consents_anon", table_name="consents")
    op.drop_table("consents")
