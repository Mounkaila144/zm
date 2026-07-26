"""Associe les audios consentis aux calculs reconnus."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_0006"
down_revision: str | None = "20260725_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("contributions") as batch:
        batch.add_column(
            sa.Column(
                "recognition_id",
                sa.Uuid(),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "source",
                sa.String(length=32),
                nullable=False,
                server_default="prompted",
            )
        )
        batch.create_foreign_key(
            "fk_contributions_recognition",
            "recognitions",
            ["recognition_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_unique_constraint(
            "uq_contributions_recognition_id",
            ["recognition_id"],
        )
        batch.create_check_constraint(
            "ck_contributions_source",
            "source IN ('prompted', 'calculation')",
        )


def downgrade() -> None:
    with op.batch_alter_table("contributions") as batch:
        batch.drop_constraint("ck_contributions_source", type_="check")
        batch.drop_constraint("uq_contributions_recognition_id", type_="unique")
        batch.drop_constraint("fk_contributions_recognition", type_="foreignkey")
        batch.drop_column("source")
        batch.drop_column("recognition_id")
