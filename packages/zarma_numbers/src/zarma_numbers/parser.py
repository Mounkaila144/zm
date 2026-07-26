"""Parseur ``zarma → nombre`` (story 1.6) — inverse déterministe du générateur.

``parse(text) -> int | None`` analyse un texte zarma (normalisé en interne par
sécurité) et retourne l'entier correspondant, ou ``None`` si le texte n'est pas
un nombre zarma valide. Le parseur ne **devine jamais** un nombre : texte non
numérique, token inconnu ou structure invalide → ``None`` (via ``ParseError``
interne portant un code). Aucun fuzzy matching : les paires proches
(``hinka``=2 / ``hinza``=3) restent distinctes.

Grammaire (miroir exact de ``generator.py``) :

    number        = zero | below_million | millions
    below_100     = unit | tens [cindi unit]
    below_1000    = hundred_group [nda below_100] | below_100
    hundred_group = zangou [unit_multiplier]
    below_million = zambar below_1000 [nda [dala] below_1000] | below_1000
    millions      = million [below_million] [nda [dala] below_million]

``millions`` réutilise **le même mécanisme** que ``below_million`` (multiplicateur
+ reste + marqueur ``dala``), juste une échelle au-dessus — aucune règle
nouvelle, par symétrie stricte avec ``generator.py``.
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
    # Le connecteur de groupes a deux formes en distribution complémentaire :
    # `da` (général) et `di` (devant 2, 3, 4, 5, 10, avec élision). Les deux sont
    # acceptés indifféremment à l'analyse — la distribution est une contrainte de
    # *génération*, pas de reconnaissance.
    groups_elided = lex.connectors.get("groups_elided")
    nda = frozenset(
        {groups.canonical, *groups.variants}
        | ({groups_elided.canonical, *groups_elided.variants} if groups_elided else set())
    )
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


#: Tokens qui peuvent démarrer un ``below_1000`` (dizaine/unité/centaine).
def _starts_below_1000(token: str | None, tab: _Tables) -> bool:
    return token is not None and (token in tab.units or token in tab.tens or token == tab.hundred)


#: Tokens qui peuvent démarrer un ``below_million`` (idem + le millier).
def _starts_below_million(token: str | None, tab: _Tables) -> bool:
    return _starts_below_1000(token, tab) or token == tab.thousand


def _parse_scaled_remainder(
    cur: _Cursor, tab: _Tables, multiplier: int, parse_remainder, starts_remainder
) -> int:
    """Consomme ``[nda [dala] <reste>]`` pour **ce** niveau, à la condition —
    et seulement à la condition — que ``multiplier`` déclenche ``dala`` côté
    générateur (``multiplier % 100 == 0 and multiplier >= 100``, cf.
    ``_compose_scaled``). Sans ce contrôle, un ``nda dala`` destiné au niveau
    *supérieur* (ex. le reste du million, après un multiplicateur en milliers
    qui n'a lui-même aucun besoin de marqueur) serait happé à tort par le
    niveau *interne* (le multiplicateur des milliers) — deux échelles peuvent
    être imbriquées et chacune ne doit consommer que son propre marqueur.
    """
    if cur.peek() not in tab.nda:
        return 0
    marker_expected = multiplier % 100 == 0 and multiplier >= 100
    saved = cur.i
    cur.advance()
    if marker_expected:
        if cur.peek() in tab.dala:
            cur.advance()
            return parse_remainder(cur, tab)
        cur.i = saved
        return 0
    if cur.peek() in tab.dala:
        # `dala` présent mais pas requis pour CE multiplicateur → appartient
        # nécessairement à un niveau englobant.
        cur.i = saved
        return 0
    if starts_remainder(cur.peek(), tab):
        return parse_remainder(cur, tab)
    cur.i = saved
    return 0


def _parse_below_million(cur: _Cursor, tab: _Tables) -> int:
    if cur.peek() == tab.thousand:
        cur.advance()
        if cur.peek() is None:
            raise ParseError("'zambar' sans multiplicateur.", code="MISSING_MULTIPLIER")
        thousands = _parse_below_1000(cur, tab)
        value = 1000 * thousands
        value += _parse_scaled_remainder(cur, tab, thousands, _parse_below_1000, _starts_below_1000)
        return value
    return _parse_below_1000(cur, tab)


def _parse_number(cur: _Cursor, tab: _Tables) -> int:
    if tab.million is not None and cur.peek() == tab.million:
        cur.advance()
        # Multiplicateur optionnel (ex. « million hinka » = 2×, « million zambar
        # wey » = 10 000×) — même grammaire que le multiplicateur des milliers.
        multiplier = 1
        if _starts_below_million(cur.peek(), tab):
            multiplier = _parse_below_million(cur, tab)
        value = 1_000_000 * multiplier
        value += _parse_scaled_remainder(
            cur, tab, multiplier, _parse_below_million, _starts_below_million
        )
        return value
    return _parse_below_million(cur, tab)


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
