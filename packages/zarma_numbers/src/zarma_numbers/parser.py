"""Parseur ``zarma → nombre`` (story 1.6) — inverse déterministe du générateur.

``parse(text) -> int | None`` analyse un texte zarma (normalisé en interne par
sécurité) et retourne l'entier correspondant, ou ``None`` si le texte n'est pas
un nombre zarma valide. Le parseur ne **devine jamais** un nombre : texte non
numérique, token inconnu ou structure invalide → ``None`` (via ``ParseError``
interne portant un code). Aucun fuzzy matching : les paires proches
(``hinka``=2 / ``hinza``=3) restent distinctes.

Grammaire (miroir exact de ``generator.py``) :

    number        = zero | below_thousand | thousands
    below_100     = unit | tens [cindi unit]
    below_1000    = hundred_group [nda below_100] | below_100
    hundred_group = zangou [unit_multiplier]
    thousands     = zambar below_1000 [nda below_1000]

Note d'ambiguïté : pour ``n ≥ 100 000`` le multiplicateur des milliers peut
contenir des centaines et un ``nda`` interne qui entre en collision avec le
séparateur multiplicateur/reste (ex. ``100 005`` et ``105 000`` produisent la
même chaîne). Ce sont précisément des formes **grandes échelles non résolues**
(cf. lexique) ; l'invariant (``validator.py``) est prouvé sur la plage résolue
non ambiguë ``0``–``99 999`` et trace le reste.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from .exceptions import ParseError
from .loader import load_lexicon
from .normalizer import normalize


@dataclass(frozen=True)
class ParseCandidate:
    """Un candidat de parsing (déterministe → confiance 1.0)."""

    value: int
    confidence: float = 1.0
    source: str = "grammar"


@dataclass(frozen=True)
class ParseResult:
    """Résultat détaillé (interface secondaire, pour l'API — Epic 2)."""

    best: ParseCandidate | None
    alternatives: list[ParseCandidate] = field(default_factory=list)
    accepted: bool = False
    error_code: str | None = None


@dataclass(frozen=True)
class _Tables:
    zero: str
    units: dict[str, int]
    tens: dict[str, int]
    cindi: str
    nda: frozenset[str]
    dala: frozenset[str]
    hundred: str
    thousand: str
    million: str | None
    known: frozenset[str]


@lru_cache(maxsize=1)
def _tables() -> _Tables:
    lex = load_lexicon()
    units: dict[str, int] = {}
    for digit, unit in lex.units.items():
        units[unit.isolated] = digit
        units[unit.combined] = digit
    tens = {term.canonical: value for value, term in lex.tens.items()}
    cindi = lex.connectors["tens_unit"].canonical
    groups = lex.connectors["groups"]
    nda = frozenset({groups.canonical, *groups.variants})
    remainder = lex.connectors.get("remainder")
    dala = frozenset({remainder.canonical, *remainder.variants}) if remainder else frozenset()
    hundred = lex.scales["hundred"].canonical
    thousand = lex.scales["thousand"].canonical
    million_scale = lex.scales.get("million")
    million = million_scale.canonical if million_scale else None
    known = frozenset(
        {lex.zero.canonical, cindi, hundred, thousand, *units, *tens, *nda, *dala}
        | ({million} if million else set())
    )
    return _Tables(
        zero=lex.zero.canonical,
        units=units,
        tens=tens,
        cindi=cindi,
        nda=nda,
        dala=dala,
        hundred=hundred,
        thousand=thousand,
        million=million,
        known=known,
    )


class _Cursor:
    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self.i = 0

    def peek(self) -> str | None:
        return self._tokens[self.i] if self.i < len(self._tokens) else None

    def advance(self) -> str:
        token = self._tokens[self.i]
        self.i += 1
        return token

    def done(self) -> bool:
        return self.i >= len(self._tokens)


def _parse_below_100(cur: _Cursor, tab: _Tables) -> int:
    token = cur.peek()
    if token is None:
        raise ParseError("Nombre incomplet.", code="INVALID_TOKEN_ORDER")
    if token in tab.tens:
        value = tab.tens[token]
        cur.advance()
        if cur.peek() == tab.cindi:
            cur.advance()
            unit = cur.peek()
            if unit is None or unit not in tab.units:
                raise ParseError(
                    "Connecteur 'cindi' non suivi d'une unité.",
                    code="INVALID_TOKEN_ORDER",
                )
            cur.advance()
            return value + tab.units[unit]
        return value
    if token in tab.units:
        cur.advance()
        return tab.units[token]
    _raise_for_token(token, tab)


def _parse_below_1000(cur: _Cursor, tab: _Tables) -> int:
    if cur.peek() == tab.hundred:
        cur.advance()
        value = 100
        multiplier = cur.peek()
        if multiplier in tab.units:
            value = 100 * tab.units[multiplier]
            cur.advance()
        # Reste optionnel : nda below_100 — uniquement si le token après nda est
        # bien un début de below_100 (dizaine/unité), sinon le nda appartient au
        # niveau supérieur (séparateur multiplicateur/reste des milliers).
        if cur.peek() in tab.nda:
            saved = cur.i
            cur.advance()
            following = cur.peek()
            if following in tab.tens or following in tab.units:
                value += _parse_below_100(cur, tab)
            else:
                cur.i = saved
        return value
    return _parse_below_100(cur, tab)


def _parse_number(cur: _Cursor, tab: _Tables) -> int:
    if tab.million is not None and cur.peek() == tab.million:
        cur.advance()
        # Multiplicateur unité optionnel (ex. « million fo » = 1×, « million hinka » = 2×).
        multiplier = 1
        nxt = cur.peek()
        if nxt in tab.units:
            multiplier = tab.units[nxt]
            cur.advance()
        return 1_000_000 * multiplier
    if cur.peek() == tab.thousand:
        cur.advance()
        if cur.peek() is None:
            raise ParseError("'zambar' sans multiplicateur.", code="MISSING_MULTIPLIER")
        value = 1000 * _parse_below_1000(cur, tab)
        if cur.peek() in tab.nda:
            cur.advance()
            # Marqueur de reste « dala » optionnel (désambiguïsation ≥ 100 000).
            if cur.peek() in tab.dala:
                cur.advance()
            value += _parse_below_1000(cur, tab)
        return value
    return _parse_below_1000(cur, tab)


def _raise_for_token(token: str, tab: _Tables) -> None:
    if token in tab.known:
        raise ParseError(f"Token '{token}' à une position invalide.", code="INVALID_TOKEN_ORDER")
    raise ParseError(f"Token inconnu : '{token}'.", code="UNKNOWN_TOKEN")


def _parse(text: str) -> int:
    if not isinstance(text, str):
        raise ParseError("Entrée non textuelle.", code="EMPTY_INPUT")
    normalized = normalize(text)
    if not normalized:
        raise ParseError("Entrée vide.", code="EMPTY_INPUT")
    tokens = normalized.split(" ")
    tab = _tables()

    if not any(token in tab.known for token in tokens):
        raise ParseError("Texte non numérique.", code="NON_NUMERIC_SPEECH")

    cur = _Cursor(tokens)
    if tokens == [tab.zero]:
        return 0

    value = _parse_number(cur, tab)

    if not cur.done():
        leftover = cur.peek()
        if leftover in (tab.thousand, tab.hundred):
            raise ParseError(f"Échelle dupliquée : '{leftover}'.", code="DUPLICATE_SCALE")
        _raise_for_token(leftover, tab)
    return value


def parse(text: str) -> int | None:
    """Interface **primaire** : retourne l'entier, ou ``None`` si non valide.

    Ne lève pas d'exception sur un texte invalide — retourne ``None`` (absence
    explicite). Ne devine **jamais** un nombre.
    """
    try:
        return _parse(text)
    except ParseError:
        return None


def parse_detailed(text: str) -> ParseResult:
    """Interface **secondaire** : résultat typé (valeur/accepté/code d'erreur)."""
    try:
        value = _parse(text)
        return ParseResult(best=ParseCandidate(value=value), accepted=True, error_code=None)
    except ParseError as exc:
        return ParseResult(best=None, accepted=False, error_code=exc.code)


__all__ = ["parse", "parse_detailed", "ParseResult", "ParseCandidate"]
