"""Borne la longueur des colonnes indexées et énumérées (portabilité MySQL).

MySQL **refuse** d'indexer une colonne ``TEXT`` sans longueur de clé
(« BLOB/TEXT column used in key specification without a key length ») : quatre
index du schéma initial rendaient donc la base impossible à créer sous MySQL.

Les colonnes concernées ont toutes une longueur naturellement bornée — UUID
textuel, empreinte SHA-256, valeur d'énumération encadrée par un
``CheckConstraint``, identifiant de version. Leur donner cette longueur n'est pas
une concession à MySQL : c'est l'information qui manquait, et indexer du ``TEXT``
est de toute façon une mauvaise pratique sous PostgreSQL comme ailleurs.

Le texte **libre** (transcriptions, consignes, métadonnées d'appareil) reste en
``Text`` : il n'est jamais indexé.

SQLite ne connaît pas ``ALTER COLUMN`` : on passe donc par ``batch_alter_table``,
qui recrée la table proprement. Le schéma reste ainsi **identique aux modèles sur
les trois moteurs** — condition pour qu'``alembic check`` ne signale aucune
dérive (c'est ce garde-fou qui a rattrapé une première version de cette
migration, laquelle sautait SQLite et laissait le schéma divergent).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260725_0005"
down_revision: str | None = "20260725_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (table, colonne, longueur, nullable) — cf. les constantes de ``db/models.py``.
_BOUNDED: tuple[tuple[str, str, int, bool], ...] = (
    ("recognitions", "anon_id", 36, False),
    ("recognitions", "decision", 32, False),
    ("recognitions", "model_version", 64, False),
    ("recognitions", "grammar_version", 64, False),
    ("feedbacks", "anon_id", 36, False),
    ("feedbacks", "feedback_type", 32, False),
    ("feedbacks", "model_version", 64, False),
    ("feedbacks", "grammar_version", 64, False),
    ("consents", "anon_id", 36, False),
    ("consents", "consent_version", 64, False),
    ("contributions", "anon_id", 36, False),
    ("contributions", "speaker_key", 64, False),
    ("contributions", "status", 32, False),
    ("contributions", "model_version", 64, False),
    ("contributions", "grammar_version", 64, False),
)


def _retype(*, to_bounded: bool) -> None:
    """Bascule les colonnes entre ``Text`` et ``String(n)``, table par table.

    ``batch_alter_table`` regroupe les modifications d'une même table en une
    seule reconstruction sous SQLite — et se comporte comme un ``ALTER COLUMN``
    ordinaire sous PostgreSQL et MySQL.
    """
    by_table: dict[str, list[tuple[str, int, bool]]] = {}
    for table, column, length, nullable in _BOUNDED:
        by_table.setdefault(table, []).append((column, length, nullable))

    for table, columns in by_table.items():
        with op.batch_alter_table(table) as batch:
            for column, length, nullable in columns:
                source, target = (sa.Text(), sa.String(length=length))
                if not to_bounded:
                    source, target = target, source
                batch.alter_column(
                    column,
                    existing_type=source,
                    type_=target,
                    existing_nullable=nullable,
                )


def upgrade() -> None:
    _retype(to_bounded=True)


def downgrade() -> None:
    _retype(to_bounded=False)
