"""Le schéma reste-t-il déployable sur SQLite, PostgreSQL **et** MySQL ?

Ces tests compilent le DDL réel pour chaque dialecte, sans serveur de base : ils
attrapent en CI la classe d'erreurs qui, sinon, ne se révèle qu'au premier
`alembic upgrade` sur la machine de production.

Le cas concret qui a motivé ce fichier : MySQL refuse d'indexer une colonne
``TEXT`` sans longueur de clé (« BLOB/TEXT column used in key specification
without a key length »). Quatre index du schéma initial étaient dans ce cas —
la base était donc impossible à créer sous MySQL, sans qu'aucun test ne le dise.
"""

from __future__ import annotations

import pytest
from app.db.models import Base
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.schema import CreateIndex, CreateTable

DIALECTS = {
    "sqlite": sqlite.dialect(),
    "postgresql": postgresql.dialect(),
    "mysql": mysql.dialect(),
}

#: Types qu'aucun index ne doit toucher : MySQL les rejette sans longueur.
_UNINDEXABLE = ("TEXT", "BLOB")


@pytest.mark.parametrize("name", sorted(DIALECTS))
def test_every_table_compiles(name: str) -> None:
    dialect = DIALECTS[name]
    for table in Base.metadata.sorted_tables:
        CreateTable(table).compile(dialect=dialect)


@pytest.mark.parametrize("name", sorted(DIALECTS))
def test_every_index_compiles(name: str) -> None:
    dialect = DIALECTS[name]
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            CreateIndex(index).compile(dialect=dialect)


def test_no_index_targets_an_unbounded_text_column() -> None:
    """Le garde-fou central : aucune colonne indexée n'est du texte non borné."""
    dialect = DIALECTS["mysql"]
    offenders: list[str] = []
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            for column in index.columns:
                rendered = str(column.type.compile(dialect)).upper()
                if any(token in rendered for token in _UNINDEXABLE):
                    offenders.append(f"{index.name}.{column.name} → {rendered}")
    assert (
        not offenders
    ), "colonnes indexées de type non borné (MySQL refusera de créer l'index) : " + ", ".join(
        offenders
    )


def test_bounded_columns_are_long_enough_for_real_values() -> None:
    """Les longueurs doivent tenir les vraies valeurs, pas seulement compiler.

    Une longueur trop courte ne casse rien au déploiement : elle tronque des
    données en production, ce qui est bien pire.
    """
    columns = {
        ("recognitions", "anon_id"): 36,  # UUID canonique
        ("contributions", "speaker_key"): 64,  # SHA-256 hexadécimal
        ("recognitions", "decision"): len("confirm"),
        ("feedbacks", "feedback_type"): len("repeat_requested"),
        ("contributions", "status"): len("validated"),
    }
    for (table_name, column_name), minimum in columns.items():
        column = Base.metadata.tables[table_name].columns[column_name]
        assert column.type.length is not None, f"{table_name}.{column_name} sans longueur"
        assert column.type.length >= minimum, (
            f"{table_name}.{column_name} = {column.type.length}, "
            f"trop court pour une valeur de {minimum} caractères"
        )


def test_free_text_columns_stay_unbounded() -> None:
    """Le texte libre ne doit pas être borné : une transcription n'a pas de taille."""
    for table_name, column_name in (
        ("recognitions", "normalized_text"),
        ("recognitions", "raw_asr_text"),
        ("contributions", "expected_prompt"),
    ):
        column = Base.metadata.tables[table_name].columns[column_name]
        assert (
            getattr(column.type, "length", None) is None
        ), f"{table_name}.{column_name} ne devrait pas être borné"
