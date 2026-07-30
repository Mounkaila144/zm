"""Expressions arithmétiques zarma : analyse, évaluation, restitution (story 6.1).

Ce module complète le cœur déterministe du paquet avec une seule construction :

    EXPRESSION := NOMBRE OPÉRATEUR NOMBRE

Il reste **autonome** (stdlib + le reste du paquet) : ni FastAPI, ni ASR, ni
audio. C'est le seul endroit où une opération est évaluée — l'API, le décodeur
et le mobile s'y adressent, ils ne recalculent jamais.

Trois règles non négociables
----------------------------

- **Source unique.** Les mots d'opérateur viennent du lexique versionné
  (``operators``), leurs formes des nombres de ``generate``. Rien n'est réécrit.
- **Jamais de résultat inventé (FR21/NFR14).** Un résultat hors du domaine
  ``[0, 1 000 000]`` — négatif, dépassant, division par zéro — lève
  ``DomainError``. Aucun arrondi, aucune troncature, aucun « à peu près ».
- **Jamais de fuzzy matching.** L'analyse est exacte, token à token ; un texte
  qui n'est pas une expression valide donne ``None``, pas une supposition.

Domaine arithmétique (décision D2, locuteur natif 2026-07-25)
-------------------------------------------------------------

===================== ================================================
Cas                   Politique
===================== ================================================
Résultat négatif      **Refus** — la notion n'existe pas en zarma
Division non entière  **Division avec reste** : ``<q> ga cindi <r>``
Division par zéro     **Refus**
Dépassement > 10⁶     **Refus** (seule option fail-closed ; l'option
                      « restreindre en amont » de la story refuse aussi,
                      simplement plus tôt — cf. Dev Notes 6.1)
===================== ================================================

Le marqueur de reste est ``ga cindi``, **jamais** ``cindi`` seul : sans le
``ga``, ``waranka cindi hinza`` (23, le nombre) et « 20 reste 3 » seraient la
même chaîne. ``ga`` n'appartenant pas au lexique des nombres, les deux formes
sont distinguables — c'est ce qui rend la division avec reste possible. Ne pas
confondre avec ``dala``, qui désambiguïse tout autre chose (restes d'unités aux
grandes échelles) : deux marqueurs distincts, jamais fusionnés.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from .exceptions import DomainError, ExpressionParseError
from .generator import MAX_VALUE, MIN_VALUE, generate, generate_combined
from .loader import Lexicon, load_lexicon
from .normalizer import normalize
from .parser import parse

#: Opérations supportées : symbole -> fonction exacte sur les entiers.
#: La division est traitée à part (quotient + reste), elle n'est pas ici.
_EXACT_OPERATIONS = {
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": lambda a, b: a * b,
}

#: Symbole de la division — seule opération à pouvoir produire un reste.
DIVISION = "/"


# --------------------------------------------------------------------------- #
# Table des opérateurs (dérivée du lexique, jamais codée en dur)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _OperatorTable:
    """Formes prononcées -> symbole, et symbole -> forme canonique."""

    #: Suite de tokens (canonique **ou** variante) -> symbole arithmétique.
    by_tokens: dict[tuple[str, ...], str]
    #: Symbole -> tokens de la forme canonique (celle que produit le rendu).
    canonical_tokens: dict[str, tuple[str, ...]]
    #: Symbole -> nom lexical (``add``, ``subtract``…), pour les rapports.
    names: dict[str, str]
    #: Marqueur du reste de division, en tokens (``("ga", "cindi")``).
    remainder_marker: tuple[str, ...]


def _build_operator_table(lex: Lexicon) -> _OperatorTable:
    by_tokens: dict[tuple[str, ...], str] = {}
    canonical_tokens: dict[str, tuple[str, ...]] = {}
    names: dict[str, str] = {}
    for name, operator in sorted(lex.operators.items()):
        if operator.canonical is None:
            continue  # non résolu au lexique : inconnu du moteur, jamais deviné
        tokens = tuple(operator.canonical.split())
        canonical_tokens[operator.symbol] = tokens
        names[operator.symbol] = name
        for form in (operator.canonical, *operator.variants):
            by_tokens[tuple(form.split())] = operator.symbol

    marker = lex.connectors.get("division_remainder")
    tens_unit = lex.connectors.get("tens_unit")
    remainder_marker: tuple[str, ...] = ()
    if marker is not None and marker.canonical and tens_unit is not None and tens_unit.canonical:
        remainder_marker = (marker.canonical, tens_unit.canonical)

    return _OperatorTable(
        by_tokens=by_tokens,
        canonical_tokens=canonical_tokens,
        names=names,
        remainder_marker=remainder_marker,
    )


@lru_cache(maxsize=1)
def _table() -> _OperatorTable:
    return _build_operator_table(load_lexicon())


def supported_operators() -> dict[str, str]:
    """Symbole -> nom lexical des opérateurs **résolus** (donc utilisables).

    Un opérateur absent d'ici n'a pas de forme validée par un locuteur natif :
    il est inconnu de la grammaire, du décodeur et de l'API. Le compléter au
    lexique suffit à l'activer partout — aucun code à modifier.
    """
    return dict(_table().names)


# --------------------------------------------------------------------------- #
# Modèle
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Expression:
    """Une opération à deux opérandes entiers : ``left <symbol> right``."""

    left: int
    symbol: str
    right: int

    def __post_init__(self) -> None:
        if self.symbol not in _EXACT_OPERATIONS and self.symbol != DIVISION:
            raise ValueError(f"Opérateur inconnu : {self.symbol!r}.")

    @property
    def operator_name(self) -> str | None:
        """Nom lexical de l'opérateur (``add``…), ou ``None`` s'il n'est pas résolu."""
        return _table().names.get(self.symbol)


@dataclass(frozen=True, slots=True)
class ExpressionResult:
    """Résultat **exact** d'une expression.

    ``value`` porte le résultat entier — le quotient dans le cas d'une division
    non entière, où ``remainder`` est alors non nul. Il n'existe pas de troisième
    cas : soit le résultat est exact, soit l'évaluation a levé ``DomainError``.
    """

    expression: Expression
    value: int
    remainder: int = 0

    @property
    def exact(self) -> bool:
        """Le résultat tient-il en un seul entier (pas de reste) ?"""
        return self.remainder == 0


@dataclass(frozen=True, slots=True)
class ExpressionParseResult:
    """Résultat détaillé d'analyse (interface secondaire, pour l'API)."""

    expression: Expression | None
    accepted: bool = False
    error_code: str | None = None


# --------------------------------------------------------------------------- #
# Analyse : texte zarma -> Expression
# --------------------------------------------------------------------------- #


def _split_on_operator(
    tokens: list[str], table: _OperatorTable
) -> tuple[list[str], str, list[str]]:
    """Découpe ``tokens`` en (gauche, symbole, droite) sur l'unique opérateur.

    L'opérateur est cherché comme sous-suite exacte. Comme ses mots sont
    disjoints de ceux des nombres (vérifié à la construction de la grammaire),
    une expression valide en contient exactement une occurrence : la découpe est
    donc unique. Zéro occurrence ou plusieurs → refus, jamais un choix arbitraire.

    Une surface peut être **contenue** dans une autre (``itonton`` dans
    ``kanga itonton``) : seule la correspondance **maximale** compte — une
    correspondance dont la plage est strictement incluse dans une autre n'est
    pas une seconde occurrence, c'est la même, entendue en plus court.
    """
    matches: list[tuple[int, int, str]] = []
    for start in range(len(tokens)):
        for surface, symbol in table.by_tokens.items():
            end = start + len(surface)
            if tuple(tokens[start:end]) == surface:
                matches.append((start, end, symbol))

    def contained(start: int, end: int) -> bool:
        return any(
            other_start <= start and end <= other_end and (other_start, other_end) != (start, end)
            for other_start, other_end, _ in matches
        )

    found = [(start, end, symbol) for start, end, symbol in matches if not contained(start, end)]

    if not found:
        raise ExpressionParseError("Aucun opérateur reconnu.", code="MISSING_OPERATOR")
    if len(found) > 1:
        raise ExpressionParseError(
            f"{len(found)} opérateurs dans l'énoncé : une seule opération est supportée.",
            code="MULTIPLE_OPERATORS",
        )

    start, end, symbol = found[0]
    left, right = tokens[:start], tokens[end:]
    if not left:
        raise ExpressionParseError("Opérande gauche manquant.", code="MISSING_LEFT_OPERAND")
    if not right:
        raise ExpressionParseError("Opérande droit manquant.", code="MISSING_RIGHT_OPERAND")
    return left, symbol, right


def _parse_expression(text: str) -> Expression:
    if not isinstance(text, str):
        raise ExpressionParseError("Entrée non textuelle.", code="EMPTY_INPUT")
    normalized = normalize(text)
    if not normalized:
        raise ExpressionParseError("Entrée vide.", code="EMPTY_INPUT")

    table = _table()
    if not table.by_tokens:
        raise ExpressionParseError(
            "Aucun opérateur résolu dans le lexique.", code="NO_RESOLVED_OPERATOR"
        )

    left_tokens, symbol, right_tokens = _split_on_operator(normalized.split(" "), table)

    left = parse(" ".join(left_tokens))
    if left is None:
        raise ExpressionParseError("Opérande gauche non numérique.", code="INVALID_LEFT_OPERAND")
    right = parse(" ".join(right_tokens))
    if right is None:
        raise ExpressionParseError("Opérande droit non numérique.", code="INVALID_RIGHT_OPERAND")
    return Expression(left=left, symbol=symbol, right=right)


def parse_expression(text: str) -> Expression | None:
    """Interface **primaire** : l'expression, ou ``None`` si le texte n'en est pas une.

    Ne devine jamais : un opérande non numérique, un opérateur absent ou plusieurs
    opérateurs donnent ``None`` (absence explicite), pas une interprétation.
    """
    try:
        return _parse_expression(text)
    except ExpressionParseError:
        return None


def parse_expression_detailed(text: str) -> ExpressionParseResult:
    """Interface **secondaire** : résultat typé, avec code d'erreur exploitable."""
    try:
        return ExpressionParseResult(expression=_parse_expression(text), accepted=True)
    except ExpressionParseError as exc:
        return ExpressionParseResult(expression=None, accepted=False, error_code=exc.code)


# --------------------------------------------------------------------------- #
# Évaluation fail-closed
# --------------------------------------------------------------------------- #


def _check_operand(value: int, side: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"Opérande {side} non entier : {type(value).__name__}.")
    if value < MIN_VALUE or value > MAX_VALUE:
        raise DomainError(
            f"Opérande {side} hors du domaine [0, 1 000 000] : {value}.",
            code="OPERAND_OUT_OF_RANGE",
        )


def evaluate(expression: Expression) -> ExpressionResult:
    """Évalue ``expression`` **exactement**, ou refuse explicitement.

    :raises DomainError: résultat négatif, dépassement, division par zéro, ou
        opérande hors domaine. Ce refus est la garantie centrale de la story :
        il n'existe aucun chemin par lequel un résultat faux ou approché
        pourrait sortir d'ici (FR21/NFR14).
    """
    _check_operand(expression.left, "gauche")
    _check_operand(expression.right, "droit")

    if expression.symbol == DIVISION:
        if expression.right == 0:
            raise DomainError("Division par zéro.", code="DIVISION_BY_ZERO")
        quotient, remainder = divmod(expression.left, expression.right)
        # Le quotient d'entiers du domaine y reste toujours : aucun contrôle de
        # dépassement n'est nécessaire ici, contrairement aux autres opérations.
        return ExpressionResult(expression=expression, value=quotient, remainder=remainder)

    value = _EXACT_OPERATIONS[expression.symbol](expression.left, expression.right)
    if value < MIN_VALUE:
        raise DomainError(
            f"Résultat négatif ({value}) : la notion n'existe pas dans le domaine zarma "
            "couvert par le lexique.",
            code="NEGATIVE_RESULT",
        )
    if value > MAX_VALUE:
        raise DomainError(
            f"Résultat hors du domaine [0, 1 000 000] : {value}.",
            code="RESULT_OVERFLOW",
        )
    return ExpressionResult(expression=expression, value=value)


# --------------------------------------------------------------------------- #
# Restitution : Expression / résultat -> zarma
# --------------------------------------------------------------------------- #


def render_expression(expression: Expression) -> str:
    """Forme zarma canonique de l'énoncé (``<gauche> <opérateur> <droite>``).

    C'est **exactement** une chaîne de la grammaire des expressions : ce que le
    décodeur contraint peut produire, et ce que ``parse_expression`` relit à
    l'identique.

    :raises DomainError: si l'opérateur n'a pas de forme résolue au lexique —
        refuser vaut mieux qu'inventer un mot zarma.
    """
    tokens = _table().canonical_tokens.get(expression.symbol)
    if tokens is None:
        raise DomainError(
            f"Opérateur {expression.symbol!r} sans forme zarma validée dans le lexique.",
            code="UNRESOLVED_OPERATOR",
        )
    return f"{generate(expression.left)} {' '.join(tokens)} {generate(expression.right)}"


def render_result(result: ExpressionResult) -> str:
    """Forme zarma du résultat — entier seul, ou ``<quotient> ga cindi <reste>``.

    Le reste est rendu en forme **combinée** (``hinza``, non ``ihinza``), comme
    partout après ``cindi`` : ``waranka ga cindi hinza`` = « 20 reste 3 ».

    :raises DomainError: si le marqueur de reste n'est pas résolu au lexique.
    """
    if result.exact:
        return generate(result.value)
    marker = _table().remainder_marker
    if not marker:
        raise DomainError(
            "Marqueur de reste de division non résolu dans le lexique.",
            code="UNRESOLVED_REMAINDER_MARKER",
        )
    return f"{generate(result.value)} {' '.join(marker)} {generate_combined(result.remainder)}"


def evaluate_text(text: str) -> tuple[Expression, ExpressionResult] | None:
    """Chaîne de bout en bout : texte zarma -> (expression, résultat exact).

    Retourne ``None`` si le texte n'est pas une expression valide. Laisse au
    contraire remonter ``DomainError`` quand l'expression **est** valide mais
    que son résultat sort du domaine : les deux situations appellent des
    messages différents côté API et mobile (« je n'ai pas compris » vs.
    « je ne peux pas répondre à cette opération »).
    """
    expression = parse_expression(text)
    if expression is None:
        return None
    return expression, evaluate(expression)


__all__ = [
    "DIVISION",
    "Expression",
    "ExpressionParseResult",
    "ExpressionResult",
    "evaluate",
    "evaluate_text",
    "parse_expression",
    "parse_expression_detailed",
    "render_expression",
    "render_result",
    "supported_operators",
]
