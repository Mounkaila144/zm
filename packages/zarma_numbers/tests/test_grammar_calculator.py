"""Grammaire de la calculatrice : ``NOMBRE`` **ou** ``NOMBRE OPÉRATEUR NOMBRE``.

Le décodeur contraint ne charge qu'une grammaire à la fois. Les deux langues
préexistantes prises isolément laissaient chacune un trou en production :
``expressions`` rejetait tout nombre dicté seul, ``numbers`` rejetait tout
calcul. Cette union est la langue que l'utilisateur parle réellement.
"""

from __future__ import annotations

import pytest

from zarma_numbers import (
    evaluate,
    load_calculator_grammar,
    load_expression_grammar,
    load_grammar,
    parse,
    parse_expression,
)


@pytest.fixture(scope="module")
def grammar():
    return load_calculator_grammar()


@pytest.mark.parametrize(
    "forme",
    [
        "zangou",
        "afo",
        "zambar fo da zangou gou",
        "zambar zangou da dala gou",
        "million iwey cindi hinka da zangou gou",
    ],
)
def test_un_nombre_seul_est_accepte(grammar, forme: str) -> None:
    assert grammar.accepts(forme)
    assert parse(grammar.canonical_form(forme)) is not None


@pytest.mark.parametrize(
    "forme",
    [
        "ihinka tonton ihinza",
        "ihinka kanga itonton ihinza",
        "zangou gou kalangaybor igou",
        "iwey kan ifaysor ihinka",
        "zambar fo kanga izabou zangou hinka",
    ],
)
def test_une_operation_est_acceptee(grammar, forme: str) -> None:
    assert grammar.accepts(forme)
    expression = parse_expression(grammar.canonical_form(forme))
    assert expression is not None
    assert evaluate(expression) is not None


@pytest.mark.parametrize(
    "forme",
    [
        "ihinka kanga itonton",  # opérande droit manquant
        "kanga itonton ihinza",  # opérande gauche manquant
        "kanga itonton",  # opérateur seul
        "zambar wey",  # nombre invalide
    ],
)
def test_un_enonce_incomplet_reste_refuse(grammar, forme: str) -> None:
    """L'union n'assouplit rien d'autre : elle ajoute les nombres, pas les
    énoncés tronqués."""
    assert not grammar.accepts(forme)


def test_les_deux_grammaires_historiques_sont_inchangees() -> None:
    """L'union est une troisième langue, pas une modification des deux autres."""
    nombres, expressions = load_grammar(), load_expression_grammar()
    assert nombres.accepts("zangou")
    assert not nombres.accepts("ihinka tonton ihinza")
    assert not expressions.accepts("zangou")
    assert expressions.accepts("ihinka tonton ihinza")


def test_la_langue_de_la_calculatrice_contient_les_deux_autres() -> None:
    """Tout énoncé accepté par l'une des deux langues l'est par l'union."""
    calculatrice = load_calculator_grammar()
    for forme in ("zangou", "zambar fo da zangou gou", "ihinka tonton ihinza"):
        assert calculatrice.accepts(forme)
    assert calculatrice.kind == "calculator"
