"""Tests des expressions arithmétiques zarma (story 6.1, tasks 2 et 3).

Deux propriétés portent toute la story :

1. **Non-ambiguïté** — une suite de mots ne peut pas être à la fois un nombre et
   une opération (AC6), et une expression acceptée n'a qu'une seule lecture.
2. **Fail-closed** — l'évaluation est exacte, ou elle refuse ; jamais fausse
   (AC3/AC4, FR21/NFR14).

Les tests property-based (hypothesis) balaient la plage entière plutôt que
quelques exemples : c'est le seul moyen d'exclure un résultat faux « rare ».
"""

import re
from collections.abc import Sequence
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from zarma_numbers import expressions
from zarma_numbers.exceptions import DomainError, GrammarDerivationError
from zarma_numbers.expressions import (
    DIVISION,
    Expression,
    evaluate,
    evaluate_text,
    parse_expression,
    parse_expression_detailed,
    render_expression,
    render_result,
    supported_operators,
)
from zarma_numbers.generator import MAX_VALUE, generate
from zarma_numbers.grammar import (
    build_expression_grammar,
    load_expression_grammar,
    load_grammar,
)
from zarma_numbers.loader import load_lexicon
from zarma_numbers.parser import parse

#: Opérateurs effectivement résolus au lexique. Les quatre le sont depuis le
#: lexique 1.4.0 ; ce qui reste testé, c'est qu'une forme **non** résolue serait
#: absente plutôt que devinée (cf. ``_lexicon_without``).
RESOLVED = sorted(supported_operators())

#: Plage entièrement résolue et non ambiguë du parseur (cf. validator.py).
SAFE_MAX = 99_999


@pytest.fixture(scope="module")
def grammar():
    return load_expression_grammar()


def _lexicon_source() -> str:
    """Texte du lexique embarqué — base des variantes « empoisonnées » ci-dessous."""
    import zarma_numbers

    return (Path(zarma_numbers.__file__).parent / "lexicon.yaml").read_text(encoding="utf-8")


def _lexicon_without(tmp_path: Path, names: Sequence[str], filename: str = "stripped.yaml") -> Path:
    """Copie du lexique où les opérateurs ``names`` redeviennent non résolus.

    Les quatre opérateurs sont désormais validés au lexique livré. Pour continuer
    de prouver que le système **refuse** au lieu d'inventer, il faut donc simuler
    l'absence — sinon la garantie ne serait plus testée nulle part le jour où une
    cinquième opération apparaîtra.
    """
    text = _lexicon_source()
    for name in names:
        pattern = rf'(?m)^(  {name}: \{{ symbol: "[^"]+", canonical: )[^,]+'
        updated = re.sub(pattern, r"\1null", text)
        assert updated != text, f"opérateur '{name}' introuvable dans le lexique"
        text = updated
    path = tmp_path / filename
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def engine_without_division(tmp_path, monkeypatch):
    """Fait tourner le moteur avec un lexique où la division n'est pas résolue."""
    path = _lexicon_without(tmp_path, ["divide"])
    monkeypatch.setattr(expressions, "load_lexicon", lambda: load_lexicon(path))
    expressions._table.cache_clear()
    try:
        yield load_lexicon(path)
    finally:
        expressions._table.cache_clear()


# --------------------------------------------------------------------------- #
# Task 1 — le lexique porte les opérateurs, résolus ou non
# --------------------------------------------------------------------------- #


def test_lexicon_declares_the_four_operators():
    operators = load_lexicon().operators
    assert {op.symbol for op in operators.values()} == {"+", "-", "*", "/"}


def test_the_four_operators_are_resolved_today():
    """Depuis le lexique 1.4.0, les quatre opérations ont une forme validée."""
    assert set(supported_operators()) == {"+", "-", "*", "/"}
    assert all(op.resolved for op in load_lexicon().operators.values())


def test_an_unresolved_operator_is_absent_never_invented(tmp_path):
    """La garantie de fond : sans forme validée, l'opération n'existe pas.

    Testée sur un lexique où la division est retirée — c'est ce mécanisme qui a
    tenu × et ÷ hors du système jusqu'à leur validation, et qui protégera la
    prochaine opération ajoutée.
    """
    lexicon = load_lexicon(_lexicon_without(tmp_path, ["divide"]))
    assert lexicon.operators["divide"].canonical is None
    assert "/" not in {op.symbol for op in lexicon.resolved_operators().values()}

    grammar = build_expression_grammar(lexicon)
    assert grammar.operator_tokens == {"tonton", "zabou", "ingaybor"}
    assert "inafaysor" not in grammar.tokens


def test_grammar_version_carries_the_operators():
    assert load_lexicon().grammar_version == "1.4.0"


# --------------------------------------------------------------------------- #
# Task 2 (AC1/AC6) — grammaire des expressions et non-ambiguïté
# --------------------------------------------------------------------------- #


def test_operator_words_are_disjoint_from_number_words(grammar):
    """Le cœur de l'AC6 : aucun mot d'opérateur n'appartient à un nombre.

    C'est cette disjonction qui garantit une découpe unique
    ``gauche | opérateur | droite`` — donc une lecture unique.
    """
    assert grammar.operator_tokens
    assert grammar.operator_tokens.isdisjoint(load_grammar().tokens)


def test_nda_is_not_an_operator(grammar):
    """Le risque nommé par la story : `nda` (« et ») ne doit pas être l'addition.

    Sinon ``zangou nda gou`` serait à la fois *105* et *100 + 5*.
    """
    connectors = load_lexicon().connectors
    forms = {c.canonical for c in connectors.values()} | {
        v for c in connectors.values() for v in c.variants
    }
    assert grammar.operator_tokens.isdisjoint(forms)


def test_a_number_alone_is_not_an_expression(grammar):
    assert grammar.accepts(generate(23)) is False


def test_a_dangling_operator_is_not_an_expression(grammar):
    for symbol in RESOLVED:
        text = render_expression(Expression(23, symbol, 15))
        prefix = text.rsplit(" ", 1)[0]  # ampute le dernier mot de l'opérande droit
        assert grammar.accepts(prefix) is False


def test_expression_grammar_rejects_two_operators(grammar):
    left = render_expression(Expression(2, RESOLVED[0], 3))
    tail = render_expression(Expression(4, RESOLVED[0], 5))
    assert grammar.accepts(f"{left} {tail}") is False


def test_build_fails_when_an_operator_collides_with_a_number_word(tmp_path):
    """Un opérateur qui serait aussi un connecteur doit faire ÉCHOUER la construction.

    C'est la vérification mécanique de l'AC6 : on ne suppose pas la disjonction,
    on la teste à chaque build et on refuse d'assembler un automate ambigu.
    """
    poisoned = _lexicon_source().replace("canonical: tonton", "canonical: cindi")
    text = _lexicon_source()
    assert poisoned != text
    path = tmp_path / "poisoned.yaml"
    path.write_text(poisoned, encoding="utf-8")

    with pytest.raises(GrammarDerivationError, match="ambigu"):
        build_expression_grammar(load_lexicon(path))


def test_build_fails_when_no_operator_is_resolved(tmp_path):
    """Aucun opérateur résolu → échec explicite, pas un automate vide silencieux."""
    path = _lexicon_without(
        tmp_path, ["add", "subtract", "multiply", "divide"], filename="no_operator.yaml"
    )
    with pytest.raises(GrammarDerivationError, match="Aucun opérateur résolu"):
        build_expression_grammar(load_lexicon(path))


@settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    left=st.integers(min_value=0, max_value=SAFE_MAX),
    right=st.integers(min_value=0, max_value=SAFE_MAX),
    symbol=st.sampled_from(RESOLVED),
)
def test_invariant_rendered_expression_is_accepted_and_reparses(left, right, symbol):
    """Invariant de la task 2 : rendu → accepté par l'automate → relu à l'identique."""
    grammar = load_expression_grammar()
    expression = Expression(left, symbol, right)
    text = render_expression(expression)

    assert grammar.accepts(text)
    assert grammar.canonical_form(text) == text
    assert parse_expression(text) == expression


@settings(max_examples=100, deadline=None)
@given(
    left=st.integers(min_value=0, max_value=SAFE_MAX),
    right=st.integers(min_value=0, max_value=SAFE_MAX),
    symbol=st.sampled_from(RESOLVED),
)
def test_an_expression_is_never_readable_as_a_number(left, right, symbol):
    """AC6, versant sémantique : aucune expression ne se lit comme un nombre."""
    assert parse(render_expression(Expression(left, symbol, right))) is None


def test_pronunciation_variants_converge_on_the_canonical_operator(grammar):
    lexicon = load_lexicon()
    for operator in lexicon.operators.values():
        if not operator.resolved:
            continue
        for variant in operator.variants:
            spoken = f"{generate(23)} {variant} {generate(15)}"
            assert grammar.canonical_form(spoken) == render_expression(
                Expression(23, operator.symbol, 15)
            )


# --------------------------------------------------------------------------- #
# Task 3 (AC3/AC4) — évaluation exacte ou refus explicite
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("left", "symbol", "right", "value"),
    [
        (23, "+", 15, 38),
        (0, "+", 0, 0),
        (100, "-", 100, 0),
        (1_000_000, "-", 1, 999_999),
    ],
)
def test_exact_results(left, symbol, right, value):
    result = evaluate(Expression(left, symbol, right))
    assert result.value == value
    assert result.exact


@pytest.mark.parametrize(
    ("left", "symbol", "right", "code"),
    [
        (3, "-", 5, "NEGATIVE_RESULT"),
        (1_000_000, "+", 1, "RESULT_OVERFLOW"),
        (2_000, "*", 2_000, "RESULT_OVERFLOW"),
        (5, "/", 0, "DIVISION_BY_ZERO"),
    ],
)
def test_out_of_domain_is_refused_with_an_explicit_code(left, symbol, right, code):
    with pytest.raises(DomainError) as excinfo:
        evaluate(Expression(left, symbol, right))
    assert excinfo.value.code == code


def test_operand_out_of_range_is_refused():
    with pytest.raises(DomainError) as excinfo:
        evaluate(Expression(MAX_VALUE + 1, "+", 0))
    assert excinfo.value.code == "OPERAND_OUT_OF_RANGE"


def test_division_with_remainder_uses_the_ga_cindi_marker():
    result = evaluate(Expression(23, DIVISION, 5))
    assert (result.value, result.remainder) == (4, 3)
    assert render_result(result) == "itaci ga cindi hinza"


def test_the_remainder_form_is_not_the_number_form():
    """Le `ga` est ce qui distingue « 20 reste 3 » du nombre 23.

    Sans lui les deux chaînes seraient identiques et la division avec reste
    serait impossible — c'est le point structurant de la décision D2.
    """
    result = evaluate(Expression(103, DIVISION, 5))
    assert (result.value, result.remainder) == (20, 3)

    remainder_form = render_result(result)
    assert remainder_form == "waranka ga cindi hinza"  # « 20 reste 3 »
    assert parse(remainder_form) is None
    assert parse(remainder_form.replace(" ga ", " ")) == 23  # le nombre 23


def test_exact_division_has_no_remainder_marker():
    result = evaluate(Expression(40, DIVISION, 8))
    assert result.exact
    assert render_result(result) == generate(5)


@settings(max_examples=500, deadline=None)
@given(
    left=st.integers(min_value=0, max_value=MAX_VALUE),
    right=st.integers(min_value=0, max_value=MAX_VALUE),
    symbol=st.sampled_from(["+", "-", "*", "/"]),
)
def test_evaluation_is_exact_or_refused_never_wrong(left, right, symbol):
    """Propriété centrale de la story : aucun résultat faux ne peut sortir.

    Soit l'évaluation refuse (``DomainError``), soit son résultat reconstitue
    **exactement** l'opération — y compris le reste d'une division.
    """
    expression = Expression(left, symbol, right)
    try:
        result = evaluate(expression)
    except DomainError:
        return  # refus explicite : c'est un comportement attendu, pas un échec

    assert 0 <= result.value <= MAX_VALUE
    if symbol == DIVISION:
        assert 0 <= result.remainder < right
        assert result.value * right + result.remainder == left
    else:
        assert result.remainder == 0
        assert result.value == {"+": left + right, "-": left - right, "*": left * right}[symbol]


@settings(max_examples=300, deadline=None)
@given(
    left=st.integers(min_value=0, max_value=MAX_VALUE),
    right=st.integers(min_value=1, max_value=MAX_VALUE),
)
def test_division_result_is_always_pronounceable(left, right):
    """Un résultat de division doit toujours pouvoir être *dit* — sinon il est inutile."""
    rendered = render_result(evaluate(Expression(left, DIVISION, right)))
    assert rendered and not rendered.startswith(" ")


# --------------------------------------------------------------------------- #
# Analyse : jamais de supposition
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("", "EMPTY_INPUT"),
        ("waranka cindi hinza", "MISSING_OPERATOR"),
        ("tonton iwey", "MISSING_LEFT_OPERAND"),
        ("iwey tonton", "MISSING_RIGHT_OPERAND"),
        ("iwey tonton zambar", "INVALID_RIGHT_OPERAND"),
        ("iwey tonton afo tonton afo", "MULTIPLE_OPERATORS"),
    ],
)
def test_invalid_expressions_are_refused_with_a_code(text, code):
    assert parse_expression(text) is None
    assert parse_expression_detailed(text).error_code == code


def test_evaluate_text_end_to_end():
    expression, result = evaluate_text("waranka cindi hinza tonton iwey cindi igou")
    assert expression == Expression(23, "+", 15)
    assert result.value == 38
    assert render_result(result) == generate(38)


def test_evaluate_text_returns_none_on_non_expression():
    assert evaluate_text("waranka cindi hinza") is None


def test_evaluate_text_propagates_domain_refusal():
    """Texte compris mais résultat impossible : ce n'est pas la même erreur."""
    with pytest.raises(DomainError):
        evaluate_text("ihinza zabou igou")


def test_render_refuses_an_unresolved_operator(engine_without_division):
    """Mieux vaut refuser de prononcer que fabriquer un mot zarma."""
    assert render_expression(Expression(2, "+", 3))  # les autres restent rendus
    with pytest.raises(DomainError, match="sans forme zarma validée"):
        render_expression(Expression(2, DIVISION, 3))


def test_an_unresolved_operator_cannot_be_heard_either(engine_without_division):
    """Sans forme validée, l'analyse ne reconnaît pas non plus l'opération."""
    assert parse_expression("ihinza inafaysor afo") is None
