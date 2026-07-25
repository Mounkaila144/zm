"""Générateur ``nombre → zarma`` : forme canonique d'un entier de 0 à 1 000 000.

Toutes les formes proviennent du ``Lexicon`` (story 1.3) — **aucune forme n'est
codée en dur** ici. Règle absolue : **jamais de forme inventée**. Si une brique
nécessaire est ``unresolved`` (``canonical: null``, ex. le million), le
générateur refuse explicitement (``UnresolvedFormError``).

Grammaire de composition (documentée en 1.2) :

    0          → yaamo
    1..9       → unité (forme isolée)
    10..99     → dizaine [cindi unité_combinée]
    100..999   → zangou [unité_combinée] [nda reste_1_99]
    1 000..999 999
               → zambar <multiplicateur 1..999> [nda reste_1_999]
    1 000 000  → forme million NON RÉSOLUE → refus explicite
"""

from __future__ import annotations

from functools import lru_cache

from .exceptions import OutOfRangeError, UnresolvedFormError
from .loader import Lexicon, load_lexicon

MIN_VALUE = 0
MAX_VALUE = 1_000_000


@lru_cache(maxsize=1)
def _lexicon() -> Lexicon:
    """Lexique embarqué, chargé une seule fois (source unique de vérité)."""
    return load_lexicon()


def generate(n: int) -> str:
    """Retourne la forme zarma canonique de ``n`` (entier de 0 à 1 000 000).

    :raises TypeError: si ``n`` n'est pas un entier (pas de coercition silencieuse).
    :raises OutOfRangeError: si ``n`` est hors de ``[0, 1 000 000]``.
    :raises UnresolvedFormError: si la composition exige une forme non résolue
        dans le lexique (ex. le million).
    """
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError(f"generate() attend un entier, reçu {type(n).__name__}.")
    if n < MIN_VALUE or n > MAX_VALUE:
        raise OutOfRangeError(f"Nombre hors plage [0, 1 000 000] : {n}.")

    lex = _lexicon()

    if n == 0:
        return lex.zero.canonical

    if n == MAX_VALUE:
        million = lex.scales.get("million")
        if million is None or million.canonical is None:
            raise UnresolvedFormError(
                "Forme du million non résolue dans le lexique : génération refusée.",
                code="UNRESOLVED_MILLION_FORM",
            )
        return million.canonical

    if 1 <= n <= 9:
        # Nombre-unité seul → forme ISOLÉE.
        return lex.units[n].isolated

    return _compose_below_million(n, lex)


def generate_combined(n: int) -> str:
    """Forme de ``n`` en position **combinée**, c'est-à-dire après un connecteur.

    Identique à ``generate`` partout sauf sur 1..9, où le zarma emploie la forme
    combinée et non la forme isolée : ``waranka cindi hinza`` (23), jamais
    ``waranka cindi ihinza``. C'est exactement la forme dont a besoin le reste
    d'une division (``… ga cindi <reste>``, story 6.1) — d'où son extraction ici,
    dans le seul module autorisé à composer des formes.

    Mêmes refus que ``generate`` : hors plage ou forme non résolue → exception.
    """
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError(f"generate_combined() attend un entier, reçu {type(n).__name__}.")
    if n < MIN_VALUE or n > MAX_VALUE:
        raise OutOfRangeError(f"Nombre hors plage [0, 1 000 000] : {n}.")
    if 1 <= n <= 9:
        return _lexicon().units[n].combined
    return generate(n)


#: Valeurs de tête qui appellent le connecteur élidé ``di`` (correction locuteur
#: 2026-07-25). Partout ailleurs le connecteur est ``da``. Table explicite : aucune
#: règle phonétique n'a été devinée — `da hakou` et `di hinka` commencent tous deux
#: par « h », la sélection ne se déduit donc pas du son.
_ELIDED_CONNECTOR_HEADS = frozenset({2, 3, 4, 5, 10})


def _leading_value(value: int) -> int:
    """Valeur du **premier mot** du groupe ``value`` (1..999).

    C'est elle qui gouverne le choix du connecteur : dans 115 = ``wey cindi gou``
    le groupe commence par 10, donc ``di`` ; dans 199 = ``wayyegga cindi yega``
    il commence par 90, donc ``da``.
    """

    if value < 10:
        return value
    if value < 100:
        return (value // 10) * 10
    return 100


def _elide_initial_i(form: str) -> str:
    """Supprime le ``i`` initial du premier mot — élision après ``di``.

    Règle énoncée par le locuteur : « lorsqu'on utilise le *di*, si le mot suivant
    commence par un *i*, on retire le *i* » (``iwey`` → ``wey``). Les formes
    combinées des unités sont déjà élidées (``hinka``, ``gou``) et restent inchangées.
    """

    head, separator, tail = form.partition(" ")
    if head.startswith("i") and len(head) > 1:
        head = head[1:]
    return f"{head}{separator}{tail}"


def _join_group(lex: Lexicon, remainder: int, rendered: str) -> str:
    """Assemble ``<connecteur> <groupe>`` en appliquant la règle da/di + élision."""

    if _leading_value(remainder) in _ELIDED_CONNECTOR_HEADS:
        connector = lex.connectors["groups_elided"].canonical
        return f"{connector} {_elide_initial_i(rendered)}"
    return f"{lex.connectors['groups'].canonical} {rendered}"


def _unit(lex: Lexicon, digit: int, *, combined: bool) -> str:
    unit = lex.units[digit]
    return unit.combined if combined else unit.isolated


def _below_100(n: int, lex: Lexicon) -> str:
    """Compose 1..99. Les unités y sont toujours en forme combinée."""
    if n < 10:
        return _unit(lex, n, combined=True)
    tens_word = lex.tens[(n // 10) * 10].canonical
    remainder = n % 10
    if remainder == 0:
        return tens_word
    cindi = lex.connectors["tens_unit"].canonical
    return f"{tens_word} {cindi} {_unit(lex, remainder, combined=True)}"


def _below_1000(n: int, lex: Lexicon) -> str:
    """Compose 1..999 (contexte multiplicateur/groupe : unités combinées)."""
    if n < 100:
        return _below_100(n, lex)
    hundred = lex.scales["hundred"]
    if hundred.canonical is None:
        raise UnresolvedFormError(
            "Forme de la centaine non résolue dans le lexique.",
            code="UNRESOLVED_HUNDRED_FORM",
        )
    hundreds_digit = n // 100
    remainder = n % 100
    parts = [hundred.canonical]
    if hundreds_digit > 1:
        parts.append(_unit(lex, hundreds_digit, combined=True))
    if remainder > 0:
        parts.append(_join_group(lex, remainder, _below_100(remainder, lex)))
    return " ".join(parts)


def _compose_below_million(n: int, lex: Lexicon) -> str:
    """Compose 10..999 999 (les unités seules 1..9 sont gérées en amont)."""
    if n < 1000:
        return _below_1000(n, lex)
    thousand = lex.scales["thousand"]
    if thousand.canonical is None:
        raise UnresolvedFormError(
            "Forme du millier non résolue dans le lexique.",
            code="UNRESOLVED_THOUSAND_FORM",
        )
    thousands = n // 1000
    remainder = n % 1000
    parts = [thousand.canonical, _below_1000(thousands, lex)]
    if remainder > 0:
        # Désambiguïsation « dala » : quand le multiplicateur des milliers est un
        # multiple de 100 (≥ 100), le reste peut être absorbé par le multiplicateur
        # (ex. 100 005 vs 105 000). Le marqueur `dala` lève l'ambiguïté.
        marker = None
        if thousands % 100 == 0 and thousands >= 100:
            remainder_marker = lex.connectors.get("remainder")
            if remainder_marker is not None and remainder_marker.canonical is not None:
                marker = remainder_marker.canonical
        rendered = _below_1000(remainder, lex)
        if marker is not None:
            # `dala` s'intercale : le connecteur porte sur lui, jamais sur le reste,
            # donc ni sélection `di` ni élision ne s'appliquent ici.
            parts.append(f"{lex.connectors['groups'].canonical} {marker} {rendered}")
        else:
            parts.append(_join_group(lex, remainder, rendered))
    return " ".join(parts)


__all__ = ["generate", "generate_combined", "MIN_VALUE", "MAX_VALUE"]
