"""Générateur ``nombre → zarma`` : forme canonique d'un entier de 0 à 99 999 999 999.

Toutes les formes proviennent du ``Lexicon`` (story 1.3) — **aucune forme n'est
codée en dur** ici. Règle absolue : **jamais de forme inventée**. Si une brique
nécessaire est ``unresolved`` (``canonical: null``), le générateur refuse
explicitement (``UnresolvedFormError``).

Grammaire de composition (documentée en 1.2, étendue au-delà du million par
**stricte analogie structurelle avec ``zambar``** — même mécanisme
multiplicateur/reste/``dala``, aucune règle nouvelle inventée) :

    0          → yaamo
    1..9       → unité (forme isolée)
    10..99     → dizaine [cindi unité_combinée]
    100..999   → zangou [unité_combinée] [nda reste_1_99]
    1 000..999 999
               → zambar <multiplicateur 1..999> [nda [dala] reste_1_999]
    1 000 000..99 999 999 999
               → million [<multiplicateur 2..99 999>] [nda [dala] reste_0_999 999]
               (``million`` seul = 1 000 000, forme déjà résolue ; le
               multiplicateur/reste réutilise tel quel le mécanisme ``zambar``)

⚠️ Au-delà de ``1 000 000``, seule la valeur exacte et le multiplicateur simple
(``million hinka`` = 2 000 000) ont été soumis à un locuteur natif (§ story
1.7). La composition avec reste à cette échelle est une **extension technique
non validée linguistiquement** — cf. ``docs/`` pour le statut de gouvernance.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from .exceptions import OutOfRangeError, UnresolvedFormError
from .loader import Lexicon, load_lexicon

MIN_VALUE = 0
#: 99 999 millions + un reste complet (< 1 000 000) : borne du multiplicateur
#: million avant qu'une échelle supérieure (non lexicalisée) ne soit requise.
MAX_VALUE = 99_999 * 1_000_000 + 999_999


@lru_cache(maxsize=1)
def _lexicon() -> Lexicon:
    """Lexique embarqué, chargé une seule fois (source unique de vérité)."""
    return load_lexicon()


def generate(n: int) -> str:
    """Retourne la forme zarma canonique de ``n`` (entier de 0 à ``MAX_VALUE``).

    :raises TypeError: si ``n`` n'est pas un entier (pas de coercition silencieuse).
    :raises OutOfRangeError: si ``n`` est hors de ``[0, MAX_VALUE]``.
    :raises UnresolvedFormError: si la composition exige une forme non résolue
        dans le lexique (ex. le million).
    """
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError(f"generate() attend un entier, reçu {type(n).__name__}.")
    if n < MIN_VALUE or n > MAX_VALUE:
        raise OutOfRangeError(f"Nombre hors plage [0, {MAX_VALUE}] : {n}.")

    lex = _lexicon()

    if n == 0:
        return lex.zero.canonical

    if 1 <= n <= 9:
        # Nombre-unité seul → forme ISOLÉE.
        return lex.units[n].isolated

    if n < 1_000_000:
        return _compose_below_million(n, lex)

    return _compose_million_and_above(n, lex)


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
        raise OutOfRangeError(f"Nombre hors plage [0, {MAX_VALUE}] : {n}.")
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


def _compose_scaled(
    n: int,
    lex: Lexicon,
    *,
    scale_value: int,
    scale_canonical: str,
    sub_compose: Callable[[int, Lexicon], str],
    omit_bare_multiplier: bool = False,
) -> str:
    """Compose ``<échelle> [<multiplicateur>] [<connecteur> [dala] <reste>]``.

    Grammaire **identique** pour ``zambar`` (mille) et ``million`` — seule
    l'échelle (``scale_value``/``scale_canonical``) et le composeur du
    multiplicateur/reste (``sub_compose``) changent. Aucune règle nouvelle :
    le marqueur ``dala`` est déclenché par la même condition que pour
    ``zambar`` (multiplicateur multiple de 100, ≥ 100) — voir le module
    docstring pour le statut de validation au-delà du million.
    """
    multiplier = n // scale_value
    remainder = n % scale_value
    parts = [scale_canonical]
    if not (omit_bare_multiplier and multiplier == 1):
        parts.append(sub_compose(multiplier, lex))
    if remainder > 0:
        # Désambiguïsation « dala » : quand le multiplicateur est un multiple
        # de 100 (≥ 100), le reste peut être absorbé par le multiplicateur
        # (ex. 100 005 vs 105 000). Le marqueur `dala` lève l'ambiguïté.
        marker = None
        if multiplier % 100 == 0 and multiplier >= 100:
            remainder_marker = lex.connectors.get("remainder")
            if remainder_marker is not None and remainder_marker.canonical is not None:
                marker = remainder_marker.canonical
        rendered = sub_compose(remainder, lex)
        if marker is not None:
            # `dala` s'intercale : le connecteur porte sur lui, jamais sur le reste,
            # donc ni sélection `di` ni élision ne s'appliquent ici.
            parts.append(f"{lex.connectors['groups'].canonical} {marker} {rendered}")
        else:
            parts.append(_join_group(lex, remainder, rendered))
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
    return _compose_scaled(
        n,
        lex,
        scale_value=1000,
        scale_canonical=thousand.canonical,
        sub_compose=_below_1000,
    )


def _compose_million_and_above(n: int, lex: Lexicon) -> str:
    """Compose ``1 000 000..MAX_VALUE`` — même mécanisme que ``zambar``.

    Le multiplicateur et le reste peuvent tous deux dépasser 999 (jusqu'à
    999 999), d'où l'appel à ``_compose_below_million`` plutôt qu'à
    ``_below_1000`` : cette fonction gère déjà correctement sa propre
    échelle interne (milliers + `dala`), y compris pour un multiplicateur
    comme 1000..99 999.
    """
    million = lex.scales.get("million")
    if million is None or million.canonical is None:
        raise UnresolvedFormError(
            "Forme du million non résolue dans le lexique : génération refusée.",
            code="UNRESOLVED_MILLION_FORM",
        )
    return _compose_scaled(
        n,
        lex,
        scale_value=1_000_000,
        scale_canonical=million.canonical,
        sub_compose=_compose_below_million,
        # 1 000 000 seul = "million" (forme déjà résolue), pas "million fo".
        omit_bare_multiplier=True,
    )


__all__ = ["generate", "generate_combined", "MIN_VALUE", "MAX_VALUE"]
