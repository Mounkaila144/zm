"""Ajout de l'opération reconnue aux métadonnées de reconnaissance (story 6.1).

Colonne **nullable** : les lignes existantes (« nombre seul », epics 1–5)
restent valides sans réécriture, et la migration inverse ne perd que la
nouveauté.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260725_0004"
down_revision: str | None = "20260724_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("recognitions", sa.Column("expression", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("recognitions", "expression")
