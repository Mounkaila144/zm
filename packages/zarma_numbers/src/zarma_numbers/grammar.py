"""Grammaire des formes valides, exploitable par un décodeur (story 5.6, task 1).

Ce module expose **la langue exacte du générateur** — l'ensemble des chaînes
``generate(n)`` pour ``n`` dans ``[0, MAX_VALUE]`` (``MAX_VALUE`` = 99 999
millions + un reste complet, cf. ``generator.py``) — sous la forme d'un
**automate fini déterministe** (DFA) sur des séquences de tokens. C'est la
structure que consomme une recherche en faisceau contrainte : à chaque état,
``next_tokens()`` donne les continuations autorisées, sans jamais énumérer
l'espace des formes.

L'échelle ``million`` suit le **même mécanisme** que l'échelle ``zambar``
(mille), une échelle au-dessus — mais sa sous-langue (multiplicateur et reste
sont des valeurs *below-million* entières, ~10⁶ formes chacune) n'est **jamais
ré-aplatie** : seules les formes < 1000 sont énumérées, la partie ≥ 1000
**réutilise la branche ``zambar`` déjà construite** comme sous-automate partagé
(cf. ``_CompositeLayer``/``_derive_composite_layer``). Chaque hypothèse de
partage est vérifiée par sondes bornées sur ``generate()`` — jamais décrétée.

Principes (non négociables) :

- **Source unique, aucune règle réécrite.** Les règles de composition ne sont
  *pas* recopiées ici : elles sont **observées** sur ``generate()`` (cf.
  ``_derive_forms``). Si le générateur change, l'automate change avec lui ; si
  une observation contredit la structure attendue, on lève
  ``GrammarDerivationError`` au lieu de deviner.
- **Jamais de forme inventée.** Une forme ``unresolved`` (``generate`` lève
  ``UnresolvedFormError``) est simplement **absente** de l'automate.
- **Aucun fuzzy matching.** L'appartenance est un parcours de transitions
  exactes ; aucune distance d'édition n'intervient (NFR14).
- **Variantes ≠ corrections ASR.** ``pronunciations`` est alimenté par les
  variantes **linguistiques** du lexique uniquement ; les ``asr_confusions``
  ne sont **jamais** lues ici (FR8).

Construction (trois étapes classiques) :

1. Un **NFA** est assemblé à partir de tries observés (formes autonomes
   ``0..999``, multiplicateurs de milliers, queues de reste, restes marqués).
   Depuis la correction locuteur (lexique 1.2.0), le connecteur de groupes est
   en distribution complémentaire (``da``/``di``) et ses continuations en
   dépendent : les queues de reste sont donc observées **connecteur inclus**
   (``('da', 'fo')``, ``('di', 'wey')``…) et c'est le trie des queues lui-même
   qui encode la dépendance connecteur → continuations. Le non-déterminisme
   reste réel : après ``zambar zangou yega da``, on peut être encore dans le
   multiplicateur (``zambar zangou yega da wayyegga`` = 990 milliers) *ou* sur
   le chemin du marqueur (``zambar zangou yega da dala fo`` = 900 001). La
   couche ``million`` ne crée pas de tries au-delà de 999 entrées : ses restes
   ≥ 1000 pointent sur les **états existants** de la branche ``zambar``.
2. Une **déterminisation par sous-ensembles** produit un DFA. La langue étant
   finie, l'automate est acyclique.
3. Une **minimisation** (fusion des états au langage résiduel identique, en
   ordre topologique inverse — l'automate est un DAG) rend le DFA publié
   minimal : les suffixes communs aux branches sont physiquement partagés.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from types import MappingProxyType

from .exceptions import GrammarDerivationError, UnresolvedFormError
from .generator import generate
from .loader import Lexicon, load_lexicon

#: Bornes des sous-langues observées sur le générateur (dérivées, pas décrétées :
#: ce sont les plages sur lesquelles on interroge ``generate``).
_BELOW_1000_MAX = 999
_THOUSAND_STEP = 1000
_MILLION_STEP = 1_000_000
#: Multiplicateur maximal du million (``MAX_VALUE // _MILLION_STEP``) et borne
#: du reste (une valeur *below_million* complète, 0..999 999).
_MILLION_MULTIPLIER_MAX = 99_999
_BELOW_MILLION_MAX = 999_999

# ---------------------------------------------------------------------------
# Observation du générateur (aucune règle de composition recopiée)
# ---------------------------------------------------------------------------


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(text.split())


def _safe_generate(n: int) -> tuple[str, ...] | None:
    """Tokens de ``generate(n)``, ou ``None`` si la forme est non résolue."""
    try:
        return _tokens(generate(n))
    except UnresolvedFormError:
        return None


def _strip_prefix(
    observed: tuple[str, ...], prefix: tuple[str, ...], context: str
) -> tuple[str, ...]:
    if observed[: len(prefix)] != prefix:
        raise GrammarDerivationError(
            f"Structure inattendue du générateur pour {context} : "
            f"{observed!r} ne commence pas par {prefix!r}."
        )
    return observed[len(prefix) :]


@dataclass(frozen=True)
class _ScaleLayer:
    """Sous-langue d'une échelle (``zambar`` ou ``million``) observée sur
    ``generate()`` — même structure pour les deux : une échelle est un
    multiplicateur (dont la forme *below*-échelle vient de la couche du
    dessous — ``standalone`` pour ``zambar``, ``standalone`` + couche
    ``zambar`` pour ``million``), plus un reste optionnel, désambiguïsé par
    ``dala`` quand le multiplicateur est un multiple de 100 (≥ 100).
    """

    #: Tokens de l'échelle (préfixe du groupe), ex. ``("zambar",)``.
    scale: tuple[str, ...]
    #: m -> forme du multiplicateur (vide si l'échelle omet le multiplicateur
    #: bare, ex. ``million`` seul pour m=1 — cf. ``omit_bare_multiplier``).
    multipliers: dict[int, tuple[str, ...]]
    #: r -> queue observée après ``<échelle> <mult(1)>``, **connecteur inclus**
    #: (``('da', 'fo')``, ``('di', 'wey')``…). C'est elle qui porte la
    #: dépendance connecteur → continuations : un ``da`` et un ``di`` ne mènent
    #: pas aux mêmes restes.
    remainder_tails: dict[int, tuple[str, ...]]
    #: m -> le marqueur de reste est-il émis pour ce multiplicateur ?
    marker_required: dict[int, bool]
    #: Préfixe observé du chemin marqué (connecteur + marqueur), si émis.
    marker_prefix: tuple[str, ...] | None
    #: r -> forme du reste sur le chemin marqué (sans connecteur ni marqueur).
    marker_remainders: dict[int, tuple[str, ...]]


@dataclass(frozen=True)
class _Derived:
    """Sous-langues observées sur ``generate()``."""

    #: n -> forme, pour les nombres qui ne passent pas par une échelle.
    standalone: dict[int, tuple[str, ...]]
    #: Couche ``zambar`` (mille), dérivée par énumération **bornée** (999+999
    #: sondes) — greffée sur la racine, et **réutilisée** par la couche million.
    thousand: _ScaleLayer | None
    #: Couche ``million``, dérivée par **composition** : formes < 1000 sondées,
    #: partie ≥ 1000 décrite en réutilisant ``thousand`` (cf. ``_CompositeLayer``).
    million: _CompositeLayer | None


def _derive_layer(
    *,
    scale_value: int,
    scale_tokens: tuple[str, ...],
    multiplier_max: int,
    remainder_max: int,
    omit_bare_multiplier: bool,
    connector_forms: set[str],
    marker: str | None,
    label: str,
) -> _ScaleLayer:
    """Dérive une couche d'échelle **en observant** ``generate()`` — même
    algorithme pour ``zambar`` (label="millier") et ``million``. Rien n'est
    décrété : chaque forme provient d'un appel au générateur, chaque découpage
    est vérifié (préfixe attendu), sans quoi on échoue.
    """
    multipliers: dict[int, tuple[str, ...]] = {}
    for m in range(1, multiplier_max + 1):
        form = _safe_generate(m * scale_value)
        if form is None:
            continue
        if omit_bare_multiplier and m == 1:
            stripped = _strip_prefix(form, scale_tokens, f"{label} multiplicateur 1")
            if stripped:
                raise GrammarDerivationError(
                    f"{label} : forme de {scale_value} inattendue {form!r} — "
                    f"multiplicateur 1 attendu vide après {scale_tokens!r}."
                )
            multipliers[1] = ()
        else:
            multipliers[m] = _strip_prefix(form, scale_tokens, f"{label} multiplicateur {m}")

    if 1 not in multipliers:
        raise GrammarDerivationError(
            f"{label} : multiplicateur 1 non résolu, grammaire indérivable."
        )

    # Queues de reste : generate(scale + r) = <échelle> <mult(1)> <queue(r)>.
    # La queue commence par le connecteur que le générateur a choisi pour r —
    # observé, jamais recalculé. Le multiplicateur 1 n'appelle aucun marqueur
    # de reste (recoupé ci-dessous).
    remainder_prefix = scale_tokens + multipliers[1]
    remainder_tails: dict[int, tuple[str, ...]] = {}
    for r in range(1, remainder_max + 1):
        form = _safe_generate(scale_value + r)
        if form is None:
            continue
        tail = _strip_prefix(form, remainder_prefix, f"{label} reste {r}")
        if not tail or tail[0] not in connector_forms:
            raise GrammarDerivationError(
                f"{label} : structure inattendue pour le reste {r} : la queue "
                f"{tail!r} ne commence pas par un connecteur de groupes "
                f"({sorted(connector_forms)})."
            )
        remainder_tails[r] = tail

    # Sondes : pour chaque connecteur observé en tête de queue, le plus petit
    # reste qui l'emploie. Vérifier chaque multiplicateur sur *toutes* les
    # sondes établit que la queue ne dépend que du reste, jamais du
    # multiplicateur — condition de validité du trie partagé.
    probes: dict[str, int] = {}
    for r in sorted(remainder_tails):
        probes.setdefault(remainder_tails[r][0], r)

    marker_required: dict[int, bool] = {}
    marker_prefix: tuple[str, ...] | None = None
    marked_probe_tails: dict[tuple[int, int], tuple[str, ...]] = {}
    for m, multiplier in multipliers.items():
        statuses: set[bool] = set()
        for probe in sorted(probes.values()):
            form = _safe_generate(m * scale_value + probe)
            if form is None:
                continue
            tail = _strip_prefix(
                form, scale_tokens + multiplier, f"{label} reste du multiplicateur {m}"
            )
            if tail == remainder_tails[probe]:
                statuses.add(False)
                continue
            if (
                marker is not None
                and len(tail) >= 2
                and tail[0] in connector_forms
                and tail[1] == marker
            ):
                if marker_prefix is None:
                    marker_prefix = tail[:2]
                elif tail[:2] != marker_prefix:
                    raise GrammarDerivationError(
                        f"{label} : préfixe marqué incohérent pour le multiplicateur {m} : "
                        f"{tail[:2]!r} au lieu de {marker_prefix!r}."
                    )
                statuses.add(True)
                marked_probe_tails[(m, probe)] = tail
                continue
            raise GrammarDerivationError(
                f"{label} : reste inattendu pour le multiplicateur {m} : {tail!r} "
                f"(ni la queue observée {remainder_tails[probe]!r}, "
                f"ni connecteur + marqueur + reste)."
            )
        if len(statuses) > 1:
            raise GrammarDerivationError(
                f"{label} : marqueur de reste incohérent pour le multiplicateur {m} : "
                "requis pour certains restes seulement."
            )
        marker_required[m] = statuses.pop() if statuses else False

    # Chemin marqué : dérivé intégralement sur le premier multiplicateur marqué,
    # puis recoupé avec les sondes des autres multiplicateurs marqués.
    marker_remainders: dict[int, tuple[str, ...]] = {}
    marked = sorted(m for m, required in marker_required.items() if required)
    if marked:
        assert marker_prefix is not None  # garanti par la boucle de détection
        marked_prefix_tokens = scale_tokens + multipliers[marked[0]] + marker_prefix
        for r in range(1, remainder_max + 1):
            form = _safe_generate(marked[0] * scale_value + r)
            if form is None:
                continue
            marker_remainders[r] = _strip_prefix(
                form, marked_prefix_tokens, f"{label} reste marqué {r}"
            )
        # Cohérence : les restes marqués (le connecteur porte sur le marqueur,
        # ni sélection di ni élision) parlent la **même sous-langue** que les
        # multiplicateurs — vérifié valeur par valeur, pas par égalité
        # d'ensembles : les deux plages ne coïncident pas forcément (le reste
        # ``million`` va jusqu'à 999 999, le multiplicateur jusqu'à 99 999
        # seulement — cf. ``MAX_VALUE``), mais pour tout entier commun aux deux
        # rôles, la forme *below-échelle* doit être identique — sauf le
        # multiplicateur 1 quand ``omit_bare_multiplier`` l'a délibérément vidé
        # (``()`` : "million" seul, cf. plus haut) : ce vide n'a de sens QUE
        # côté multiplicateur, jamais côté reste (``fo`` reste ``fo``).
        for k in sorted(set(multipliers) & set(marker_remainders)):
            if omit_bare_multiplier and k == 1 and multipliers[k] == ():
                continue
            if multipliers[k] != marker_remainders[k]:
                raise GrammarDerivationError(
                    f"{label} : la forme de {k} diffère entre multiplicateur "
                    f"({multipliers[k]!r}) et reste marqué ({marker_remainders[k]!r}) — "
                    "hypothèse de composition invalidée."
                )
        for (m, probe), tail in marked_probe_tails.items():
            if tail != marker_prefix + marker_remainders[probe]:
                raise GrammarDerivationError(
                    f"{label} : reste marqué inattendu pour le multiplicateur {m} : {tail!r}."
                )

    return _ScaleLayer(
        scale=scale_tokens,
        multipliers=multipliers,
        remainder_tails=remainder_tails,
        marker_required=marker_required,
        marker_prefix=marker_prefix,
        marker_remainders=marker_remainders,
    )


@dataclass(frozen=True)
class _CompositeLayer:
    """Couche d'échelle **composite** (``million``) : même mécanisme que
    ``zambar`` (multiplicateur + reste optionnel + marqueur ``dala``), mais le
    multiplicateur (1..99 999) et le reste (1..999 999) parlent la sous-langue
    *below-million* entière.

    Cette sous-langue n'est **pas ré-aplatie** (~10⁶ formes par rôle, ce qui
    ferait exploser l'automate) : seules les formes < 1000 sont observées
    exhaustivement — même budget borné que pour ``zambar`` — et la partie
    ≥ 1000 est décrite par **réutilisation de la couche ``zambar`` déjà
    dérivée** (mêmes formes de multiplicateur, mêmes queues). La validité de
    cette réutilisation n'est jamais supposée : elle est **vérifiée par sondes
    sur ``generate()``** (préfixes exacts, connecteur unique devant un reste
    ≥ 1000, marquage indépendant du multiplicateur zambar), et toute déviation
    lève ``GrammarDerivationError`` au lieu de deviner.
    """

    #: Tokens de l'échelle (``("million",)``). Le multiplicateur 1 est nu :
    #: l'échelle seule vaut ``scale_value`` (``omit_bare_multiplier``).
    scale: tuple[str, ...]
    #: m (2..999) -> forme below-1000 du multiplicateur.
    multipliers: dict[int, tuple[str, ...]]
    #: r (1..999) -> queue de reste observée, **connecteur inclus**.
    remainder_tails: dict[int, tuple[str, ...]]
    #: Connecteur observé devant un reste ≥ 1000 (point d'entrée de la branche
    #: ``zambar`` partagée), ``None`` si la sous-couche est absente.
    large_tail_connector: str | None
    #: Multiplicateur zambar maximal côté multiplicateur du million
    #: (``multiplier_max // 1000``) — au-delà, hors langue.
    sub_multiplier_limit: int
    #: Marquage ``dala`` observé, par **famille d'états de fin** du
    #: multiplicateur : échelle nue (m=1), formes < 1000, multiplicateurs
    #: zambar (m = m'·1000), queues zambar (m = m'·1000 + r', indépendant de
    #: m' — recoupé sur deux multiplicateurs).
    bare_marker: bool
    multiplier_marker: dict[int, bool]
    sub_multiplier_marker: dict[int, bool]
    sub_tail_marker: dict[int, bool]
    #: Préfixe observé du chemin marqué (connecteur + marqueur), si émis.
    marker_prefix: tuple[str, ...] | None
    #: r (1..999) -> forme du reste sur le chemin marqué (sans préfixe).
    marker_remainders: dict[int, tuple[str, ...]]


def _derive_composite_layer(
    *,
    scale_value: int,
    scale_tokens: tuple[str, ...],
    small_max: int,
    multiplier_max: int,
    remainder_max: int,
    sub_layer: _ScaleLayer | None,
    sub_scale_value: int,
    connector_forms: set[str],
    marker: str | None,
    label: str,
) -> _CompositeLayer:
    """Dérive la couche composite **en observant** ``generate()``, avec un
    budget de sondes borné (~15 000 appels, indépendant de ``MAX_VALUE``).

    Trois familles d'observations :

    1. exhaustives mais bornées : multiplicateurs et restes < 1000 (comme pour
       ``zambar``) ;
    2. de **réutilisation** : la partie ≥ 1000 du multiplicateur et du reste
       doit être, token pour token, la couche ``zambar`` déjà dérivée — vérifié
       sur tous les multiplicateurs zambar et toutes les queues (ancrées sur un
       multiplicateur), plus recoupements sur le plus grand multiplicateur ;
    3. de **marquage** : le marqueur ``dala`` est sondé par famille d'états de
       fin de multiplicateur, et son indépendance vis-à-vis du multiplicateur
       zambar (condition de validité du partage d'états) est recoupée sur deux
       multiplicateurs distincts.
    """
    bare = _safe_generate(scale_value)
    if bare != scale_tokens:
        raise GrammarDerivationError(
            f"{label} : forme de {scale_value} inattendue {bare!r} — "
            f"l'échelle nue {scale_tokens!r} était attendue (multiplicateur 1 omis)."
        )

    sub_limit = 0
    if sub_layer is not None:
        sub_limit = multiplier_max // sub_scale_value
        if sub_limit * sub_scale_value + small_max != multiplier_max:
            raise GrammarDerivationError(
                f"{label} : plage de multiplicateurs {multiplier_max} non couverte "
                f"par la composition (limite zambar {sub_limit})."
            )
        if small_max * sub_scale_value + small_max != remainder_max:
            raise GrammarDerivationError(
                f"{label} : plage de restes {remainder_max} non couverte par la "
                "sous-langue below-million."
            )

    # 1) Multiplicateurs < 1000 (exhaustif borné, comme pour ``zambar``).
    multipliers: dict[int, tuple[str, ...]] = {}
    for m in range(2, small_max + 1):
        form = _safe_generate(m * scale_value)
        if form is None:
            continue
        multipliers[m] = _strip_prefix(form, scale_tokens, f"{label} multiplicateur {m}")

    # 2) Queues de reste < 1000 (exhaustif borné).
    remainder_tails: dict[int, tuple[str, ...]] = {}
    for r in range(1, small_max + 1):
        form = _safe_generate(scale_value + r)
        if form is None:
            continue
        tail = _strip_prefix(form, scale_tokens, f"{label} reste {r}")
        if not tail or tail[0] not in connector_forms:
            raise GrammarDerivationError(
                f"{label} : structure inattendue pour le reste {r} : la queue "
                f"{tail!r} ne commence pas par un connecteur de groupes "
                f"({sorted(connector_forms)})."
            )
        remainder_tails[r] = tail

    probes: dict[str, int] = {}
    for r in sorted(remainder_tails):
        probes.setdefault(remainder_tails[r][0], r)
    probe_values = sorted(probes.values())

    sub_probe_values: list[int] = []
    sub_eligible: list[int] = []
    if sub_layer is not None:
        sub_probes: dict[str, int] = {}
        for r_ in sorted(sub_layer.remainder_tails):
            sub_probes.setdefault(sub_layer.remainder_tails[r_][0], r_)
        sub_probe_values = sorted(sub_probes.values())
        sub_eligible = sorted(m_ for m_ in sub_layer.multipliers if 1 <= m_ <= sub_limit)

    # 3) Réutilisation côté MULTIPLICATEUR : « million <zambar …> » doit être,
    #    token pour token, la branche zambar dérivée (restreinte à m' ≤ 99).
    if sub_layer is not None and sub_eligible:
        for m_ in sub_eligible:
            expected = scale_tokens + sub_layer.scale + sub_layer.multipliers[m_]
            observed = _safe_generate(m_ * sub_scale_value * scale_value)
            if observed != expected:
                raise GrammarDerivationError(
                    f"{label} : le multiplicateur {m_ * sub_scale_value} ne réutilise "
                    f"pas la forme zambar dérivée ({observed!r} ≠ {expected!r})."
                )
        anchor = scale_tokens + sub_layer.scale + sub_layer.multipliers[sub_eligible[0]]
        for r_ in sorted(sub_layer.remainder_tails):
            expected = anchor + sub_layer.remainder_tails[r_]
            observed = _safe_generate((sub_eligible[0] * sub_scale_value + r_) * scale_value)
            if observed != expected:
                raise GrammarDerivationError(
                    f"{label} : la queue zambar du multiplicateur "
                    f"{sub_eligible[0] * sub_scale_value + r_} n'est pas réutilisée "
                    f"telle quelle ({observed!r} ≠ {expected!r})."
                )
        top = sub_eligible[-1]
        for r_ in sub_probe_values:
            expected = (
                scale_tokens
                + sub_layer.scale
                + sub_layer.multipliers[top]
                + sub_layer.remainder_tails[r_]
            )
            observed = _safe_generate((top * sub_scale_value + r_) * scale_value)
            if observed != expected:
                raise GrammarDerivationError(
                    f"{label} : queue zambar dépendante du multiplicateur pour "
                    f"{top * sub_scale_value + r_} ({observed!r} ≠ {expected!r})."
                )

    # 4) Réutilisation côté RESTE : un reste ≥ 1000 est « <connecteur> » suivi de
    #    la branche zambar **entière** (mêmes états) — connecteur unique observé.
    large_tail_connector: str | None = None
    if sub_layer is not None:
        for m_ in sorted(sub_layer.multipliers):
            observed = _safe_generate(scale_value + m_ * sub_scale_value)
            if observed is None:
                continue
            tail = _strip_prefix(observed, scale_tokens, f"{label} reste {m_ * sub_scale_value}")
            if not tail or tail[0] not in connector_forms:
                raise GrammarDerivationError(
                    f"{label} : reste {m_ * sub_scale_value} sans connecteur de groupes : {tail!r}."
                )
            if large_tail_connector is None:
                large_tail_connector = tail[0]
            elif tail[0] != large_tail_connector:
                raise GrammarDerivationError(
                    f"{label} : connecteurs multiples devant les restes ≥ {sub_scale_value} "
                    f"({large_tail_connector!r} puis {tail[0]!r}) — partage impossible."
                )
            expected = (large_tail_connector,) + sub_layer.scale + sub_layer.multipliers[m_]
            if tail != expected:
                raise GrammarDerivationError(
                    f"{label} : le reste {m_ * sub_scale_value} n'est pas la branche "
                    f"zambar partagée ({tail!r} ≠ {expected!r})."
                )
        if large_tail_connector is not None:
            first = min(sub_layer.multipliers)
            base = (
                scale_tokens
                + (large_tail_connector,)
                + sub_layer.scale
                + sub_layer.multipliers[first]
            )
            for r_ in sorted(sub_layer.remainder_tails):
                expected = base + sub_layer.remainder_tails[r_]
                observed = _safe_generate(scale_value + first * sub_scale_value + r_)
                if observed != expected:
                    raise GrammarDerivationError(
                        f"{label} : la queue zambar du reste "
                        f"{first * sub_scale_value + r_} n'est pas réutilisée telle "
                        f"quelle ({observed!r} ≠ {expected!r})."
                    )
            marked_sub = sorted(m for m, req in sub_layer.marker_required.items() if req)
            if marked_sub and sub_layer.marker_prefix is not None:
                m_mk = marked_sub[0]
                for r_ in sub_probe_values:
                    expected = (
                        scale_tokens
                        + (large_tail_connector,)
                        + sub_layer.scale
                        + sub_layer.multipliers[m_mk]
                        + sub_layer.marker_prefix
                        + sub_layer.marker_remainders[r_]
                    )
                    observed = _safe_generate(scale_value + m_mk * sub_scale_value + r_)
                    if observed != expected:
                        raise GrammarDerivationError(
                            f"{label} : chemin marqué zambar non réutilisé dans le reste "
                            f"{m_mk * sub_scale_value + r_} ({observed!r} ≠ {expected!r})."
                        )

    # 5) Marquage ``dala`` au niveau composite, sondé par famille d'états.
    marker_prefix: tuple[str, ...] | None = None
    marked_probe_tails: list[tuple[int, int, tuple[str, ...]]] = []

    def _marked(value: int, prefix: tuple[str, ...], context: str) -> bool:
        nonlocal marker_prefix
        statuses: set[bool] = set()
        for r0 in probe_values:
            form = _safe_generate(value * scale_value + r0)
            if form is None:
                continue
            tail = _strip_prefix(form, prefix, context)
            if tail == remainder_tails[r0]:
                statuses.add(False)
                continue
            if (
                marker is not None
                and len(tail) >= 2
                and tail[0] in connector_forms
                and tail[1] == marker
            ):
                if marker_prefix is None:
                    marker_prefix = tail[:2]
                elif tail[:2] != marker_prefix:
                    raise GrammarDerivationError(
                        f"{label} : préfixe marqué incohérent pour {context} : "
                        f"{tail[:2]!r} au lieu de {marker_prefix!r}."
                    )
                statuses.add(True)
                marked_probe_tails.append((value, r0, tail))
                continue
            raise GrammarDerivationError(
                f"{label} : reste inattendu pour {context} : {tail!r} "
                f"(ni la queue observée {remainder_tails[r0]!r}, "
                "ni connecteur + marqueur + reste)."
            )
        if len(statuses) > 1:
            raise GrammarDerivationError(
                f"{label} : marqueur de reste incohérent pour {context} : "
                "requis pour certains restes seulement."
            )
        return statuses.pop() if statuses else False

    bare_marker = _marked(1, scale_tokens, f"{label} échelle nue")
    multiplier_marker = {
        m: _marked(m, scale_tokens + form, f"{label} multiplicateur {m}")
        for m, form in multipliers.items()
    }
    sub_multiplier_marker: dict[int, bool] = {}
    sub_tail_marker: dict[int, bool] = {}
    if sub_layer is not None and sub_eligible:
        for m_ in sub_eligible:
            prefix = scale_tokens + sub_layer.scale + sub_layer.multipliers[m_]
            sub_multiplier_marker[m_] = _marked(
                m_ * sub_scale_value, prefix, f"{label} multiplicateur {m_ * sub_scale_value}"
            )
        # Le marquage d'une queue zambar ne doit dépendre que de la queue (les
        # états sont partagés entre multiplicateurs) : recoupé sur le plus
        # petit ET le plus grand multiplicateur zambar.
        lo, hi = sub_eligible[0], sub_eligible[-1]
        for r_ in sorted(sub_layer.remainder_tails):
            prefix_lo = (
                scale_tokens
                + sub_layer.scale
                + sub_layer.multipliers[lo]
                + sub_layer.remainder_tails[r_]
            )
            flag = _marked(
                lo * sub_scale_value + r_,
                prefix_lo,
                f"{label} multiplicateur {lo * sub_scale_value + r_}",
            )
            if hi != lo:
                prefix_hi = (
                    scale_tokens
                    + sub_layer.scale
                    + sub_layer.multipliers[hi]
                    + sub_layer.remainder_tails[r_]
                )
                if (
                    _marked(
                        hi * sub_scale_value + r_,
                        prefix_hi,
                        f"{label} multiplicateur {hi * sub_scale_value + r_}",
                    )
                    != flag
                ):
                    raise GrammarDerivationError(
                        f"{label} : marquage de la queue zambar {r_} dépendant du "
                        "multiplicateur — partage d'états invalide."
                    )
            sub_tail_marker[r_] = flag

    # 6) Chemin marqué : restes < 1000 dérivés intégralement sur le premier
    #    multiplicateur marqué ; restes ≥ 1000 = branche zambar partagée (sondes).
    marker_remainders: dict[int, tuple[str, ...]] = {}
    rep_value: int | None = None
    rep_prefix: tuple[str, ...] | None = None
    small_marked = sorted(m for m, req in multiplier_marker.items() if req)
    if small_marked:
        rep_value = small_marked[0]
        rep_prefix = scale_tokens + multipliers[rep_value]
    elif sub_layer is not None:
        sub_marked = sorted(m_ for m_, req in sub_multiplier_marker.items() if req)
        if sub_marked:
            rep_value = sub_marked[0] * sub_scale_value
            rep_prefix = scale_tokens + sub_layer.scale + sub_layer.multipliers[sub_marked[0]]
    if rep_value is not None and rep_prefix is not None:
        if marker_prefix is None:  # pragma: no cover - incohérence interne
            raise GrammarDerivationError(f"{label} : multiplicateur marqué sans préfixe observé.")
        base = rep_prefix + marker_prefix
        for r in range(1, small_max + 1):
            form = _safe_generate(rep_value * scale_value + r)
            if form is None:
                continue
            marker_remainders[r] = _strip_prefix(form, base, f"{label} reste marqué {r}")
        for k in sorted(set(multipliers) & set(marker_remainders)):
            if multipliers[k] != marker_remainders[k]:
                raise GrammarDerivationError(
                    f"{label} : la forme de {k} diffère entre multiplicateur "
                    f"({multipliers[k]!r}) et reste marqué ({marker_remainders[k]!r}) — "
                    "hypothèse de composition invalidée."
                )
        for value, r0, tail in marked_probe_tails:
            if r0 not in marker_remainders or tail != marker_prefix + marker_remainders[r0]:
                raise GrammarDerivationError(
                    f"{label} : reste marqué inattendu pour le multiplicateur {value} : {tail!r}."
                )
        if sub_layer is not None and large_tail_connector is not None:
            for m_ in (min(sub_layer.multipliers), max(sub_layer.multipliers)):
                expected = base + sub_layer.scale + sub_layer.multipliers[m_]
                observed = _safe_generate(rep_value * scale_value + m_ * sub_scale_value)
                if observed != expected:
                    raise GrammarDerivationError(
                        f"{label} : le reste marqué {m_ * sub_scale_value} n'est pas la "
                        f"branche zambar partagée ({observed!r} ≠ {expected!r})."
                    )

    return _CompositeLayer(
        scale=scale_tokens,
        multipliers=multipliers,
        remainder_tails=remainder_tails,
        large_tail_connector=large_tail_connector,
        sub_multiplier_limit=sub_limit,
        bare_marker=bare_marker,
        multiplier_marker=multiplier_marker,
        sub_multiplier_marker=sub_multiplier_marker,
        sub_tail_marker=sub_tail_marker,
        marker_prefix=marker_prefix,
        marker_remainders=marker_remainders,
    )


def _derive_forms(lex: Lexicon) -> _Derived:
    """Dérive les sous-langues **en observant** ``generate()``.

    Rien n'est décrété ici. Deux couches d'échelle, dérivées **indépendamment**
    par le même algorithme (``_derive_layer``) : ``zambar`` (mille) et
    ``million`` — extension par stricte analogie structurelle, aucune règle
    nouvelle (cf. ``generator.py``).
    """
    standalone: dict[int, tuple[str, ...]] = {}
    for n in range(0, _BELOW_1000_MAX + 1):
        form = _safe_generate(n)
        if form is not None:
            standalone[n] = form

    # Formes du connecteur de groupes (distribution complémentaire da/di) :
    # seules têtes de queue admissibles — tout autre découpage est une erreur.
    connector_forms: set[str] = set()
    for key in ("groups", "groups_elided"):
        term = lex.connectors.get(key)
        if term is not None and term.canonical is not None:
            connector_forms.add(term.canonical)
    if not connector_forms:
        raise GrammarDerivationError("Connecteur de groupes non résolu : grammaire indérivable.")

    marker_term = lex.connectors.get("remainder")
    marker = marker_term.canonical if marker_term is not None else None

    thousand_layer: _ScaleLayer | None = None
    thousand_scale = lex.scales["thousand"].canonical
    if thousand_scale is not None and _safe_generate(_THOUSAND_STEP) is not None:
        thousand_layer = _derive_layer(
            scale_value=_THOUSAND_STEP,
            scale_tokens=_tokens(thousand_scale),
            multiplier_max=_BELOW_1000_MAX,
            remainder_max=_BELOW_1000_MAX,
            omit_bare_multiplier=False,
            connector_forms=connector_forms,
            marker=marker,
            label="millier",
        )

    million_layer: _CompositeLayer | None = None
    million_entry = lex.scales.get("million")
    million_scale = million_entry.canonical if million_entry is not None else None
    if million_scale is not None and _safe_generate(_MILLION_STEP) is not None:
        million_layer = _derive_composite_layer(
            scale_value=_MILLION_STEP,
            scale_tokens=_tokens(million_scale),
            small_max=_BELOW_1000_MAX,
            multiplier_max=_MILLION_MULTIPLIER_MAX,
            remainder_max=_BELOW_MILLION_MAX,
            sub_layer=thousand_layer,
            sub_scale_value=_THOUSAND_STEP,
            connector_forms=connector_forms,
            marker=marker,
            label="million",
        )

    return _Derived(standalone=standalone, thousand=thousand_layer, million=million_layer)


# ---------------------------------------------------------------------------
# Trie / NFA / déterminisation
# ---------------------------------------------------------------------------


@dataclass
class _Trie:
    """Trie de séquences de tokens (structure de construction, non publique)."""

    children: list[dict[str, int]] = field(default_factory=lambda: [{}])
    terminals: set[int] = field(default_factory=set)

    def child(self, node: int, token: str) -> int:
        """Enfant de ``node`` par ``token``, créé au besoin (sans le rendre terminal)."""
        nxt = self.children[node].get(token)
        if nxt is None:
            self.children.append({})
            nxt = len(self.children) - 1
            self.children[node][token] = nxt
        return nxt

    def insert(self, tokens: Sequence[str]) -> int:
        node = 0
        for token in tokens:
            node = self.child(node, token)
        self.terminals.add(node)
        return node


@dataclass
class _Nfa:
    transitions: list[dict[str, set[int]]] = field(default_factory=list)
    accepting: set[int] = field(default_factory=set)

    def new_state(self) -> int:
        self.transitions.append({})
        return len(self.transitions) - 1

    def add_edge(self, src: int, token: str, dst: int) -> None:
        self.transitions[src].setdefault(token, set()).add(dst)

    def graft(self, trie: _Trie, root: int) -> list[int]:
        """Greffe ``trie`` sur l'état ``root`` ; retourne node de trie -> état NFA.

        Les états terminaux ne sont **pas** marqués acceptants ici : c'est
        l'appelant qui décide ce qu'« accepter » veut dire. Un même sous-langage
        (les nombres) est en effet greffé deux fois dans la grammaire des
        expressions, où seul le second opérande termine l'énoncé.
        """
        mapping = [root] + [self.new_state() for _ in range(len(trie.children) - 1)]
        for node, edges in enumerate(trie.children):
            for token, child in edges.items():
                self.add_edge(mapping[node], token, mapping[child])
        return mapping

    def graft_terminals(self, trie: _Trie, root: int) -> tuple[list[int], set[int]]:
        """``graft`` + l'ensemble des états NFA correspondant à une forme complète."""
        mapping = self.graft(trie, root)
        return mapping, {mapping[node] for node in trie.terminals}


def _graft_number_language(nfa: _Nfa, root: int, derived: _Derived) -> set[int]:
    """Greffe la langue des **nombres** sur ``root``.

    Retourne les états où un nombre complet vient d'être lu. Rien n'est marqué
    acceptant : dans la grammaire des nombres ces états *sont* les acceptants ;
    dans celle des expressions, ceux de l'opérande gauche portent au contraire
    les arêtes de l'opérateur.
    """
    complete: set[int] = set()

    standalone_trie = _Trie()
    for form in derived.standalone.values():
        standalone_trie.insert(form)
    _, terminals = nfa.graft_terminals(standalone_trie, root)
    complete |= terminals

    def entry_edges(trie: _Trie) -> tuple[list[tuple[str, int]], set[int]]:
        """Greffe ``trie`` sur un état neuf ; retourne ses arêtes racine.

        Recopier ces arêtes sur chaque état de fin de multiplicateur équivaut à
        une ε-transition vers la racine du trie : le connecteur est la première
        arête du trie, donc ses continuations en dépendent par construction.
        """
        states, ends = nfa.graft_terminals(trie, nfa.new_state())
        return [(token, states[child]) for token, child in trie.children[0].items()], ends

    # Branche ``zambar`` : <échelle> <multiplicateur> [ <queue(r)> ], où la
    # queue observée inclut son connecteur (``da …`` / ``di …``), ou, pour les
    # multiplicateurs marqués, <connecteur> <marqueur> <reste plein>.
    thousand_entry: tuple[str, int] | None = None
    layer = derived.thousand
    if layer is not None:
        multiplier_trie = _Trie()
        multiplier_nodes = {
            m: multiplier_trie.insert(layer.scale + form) for m, form in layer.multipliers.items()
        }
        multiplier_states, terminals = nfa.graft_terminals(multiplier_trie, root)
        complete |= terminals

        tail_trie = _Trie()
        for tail in layer.remainder_tails.values():
            tail_trie.insert(tail)
        tail_edges, tail_ends = entry_edges(tail_trie)
        complete |= tail_ends

        marked_edges: list[tuple[str, int]] = []
        if layer.marker_prefix is not None:
            marked_trie = _Trie()
            for form in layer.marker_remainders.values():
                marked_trie.insert(layer.marker_prefix + form)
            marked_edges, marked_ends = entry_edges(marked_trie)
            complete |= marked_ends

        for m, node in multiplier_nodes.items():
            required = layer.marker_required.get(m, False)
            if required and not marked_edges:  # pragma: no cover - incohérence interne
                raise GrammarDerivationError(f"Marqueur de reste requis pour {m} mais non résolu.")
            for token, target in marked_edges if required else tail_edges:
                nfa.add_edge(multiplier_states[node], token, target)

        # Point d'entrée **partagé** de la branche zambar : la couche million y
        # renvoie ses restes ≥ 1000 (mêmes états — c'est ce partage qui garde
        # l'automate compact, cf. ``_CompositeLayer``).
        head_child = multiplier_trie.children[0].get(layer.scale[0])
        if head_child is not None:
            thousand_entry = (layer.scale[0], multiplier_states[head_child])

    if derived.million is not None:
        complete |= _graft_million_layer(
            nfa, root, derived.million, derived.thousand, thousand_entry
        )

    return complete


def _graft_million_layer(
    nfa: _Nfa,
    root: int,
    layer: _CompositeLayer,
    sub: _ScaleLayer | None,
    sub_entry: tuple[str, int] | None,
) -> set[int]:
    """Greffe la branche ``million`` sur ``root`` **sans ré-aplatir** la
    sous-langue below-million.

    - multiplicateurs < 1000 : trie observé (borné), comme pour ``zambar`` ;
    - multiplicateurs ≥ 1000 : **copie restreinte** (m' ≤ 99) des tries zambar
      déjà dérivés — copie nécessaire car ces états de fin portent une
      continuation propre (les queues ``million``), contrairement à la branche
      zambar de la racine qui, elle, termine le nombre ;
    - restes < 1000 : trie observé (borné) ;
    - restes ≥ 1000 : une **seule arête** (connecteur observé puis
      ``sub_entry``) qui renvoie dans la branche zambar existante — états
      partagés, y compris ses queues et son chemin ``dala`` interne ;
    - chemin marqué (``da dala``) : idem, formes < 1000 + arête vers la branche
      zambar partagée.

    Retourne les états où un nombre complet vient d'être lu.
    """
    complete: set[int] = set()

    multiplier_trie = _Trie()
    bare_node = multiplier_trie.insert(layer.scale)  # « million » seul = 1 000 000
    multiplier_nodes = {
        m: multiplier_trie.insert(layer.scale + form) for m, form in layer.multipliers.items()
    }
    multiplier_states, terminals = nfa.graft_terminals(multiplier_trie, root)
    complete |= terminals
    scale_state = multiplier_states[bare_node]

    # Multiplicateurs ≥ 1000 : formes zambar déjà dérivées (aucune nouvelle
    # sonde), restreintes à ``sub_multiplier_limit``.
    zm_states: list[int] = []
    zm_nodes: dict[int, int] = {}
    ztail_states: list[int] = []
    ztail_nodes: dict[int, int] = {}
    if sub is not None and layer.sub_multiplier_limit > 0:
        zm_trie = _Trie()
        zm_nodes = {
            m_: zm_trie.insert(sub.scale + sub.multipliers[m_])
            for m_ in sub.multipliers
            if 1 <= m_ <= layer.sub_multiplier_limit
        }
        zm_states, zm_terminals = nfa.graft_terminals(zm_trie, scale_state)
        complete |= zm_terminals

        ztail_trie = _Trie()
        ztail_nodes = {r_: ztail_trie.insert(tail) for r_, tail in sub.remainder_tails.items()}
        ztail_states, ztail_ends = nfa.graft_terminals(ztail_trie, nfa.new_state())
        complete |= ztail_ends
        ztail_edges = [(token, ztail_states[c]) for token, c in ztail_trie.children[0].items()]
        for node in zm_nodes.values():
            for token, target in ztail_edges:
                nfa.add_edge(zm_states[node], token, target)

    # Queues de reste : < 1000 observées ; ≥ 1000 = branche zambar partagée.
    tail_trie = _Trie()
    for tail in layer.remainder_tails.values():
        tail_trie.insert(tail)
    large_node: int | None = None
    if sub_entry is not None and layer.large_tail_connector is not None:
        large_node = tail_trie.child(0, layer.large_tail_connector)
    tail_states, tail_ends = nfa.graft_terminals(tail_trie, nfa.new_state())
    complete |= tail_ends
    tail_edges = [(token, tail_states[c]) for token, c in tail_trie.children[0].items()]
    if large_node is not None and sub_entry is not None:
        nfa.add_edge(tail_states[large_node], sub_entry[0], sub_entry[1])

    marked_edges: list[tuple[str, int]] = []
    if layer.marker_prefix is not None:
        marked_trie = _Trie()
        for form in layer.marker_remainders.values():
            marked_trie.insert(layer.marker_prefix + form)
        marked_entry_node = 0
        for token in layer.marker_prefix:
            marked_entry_node = marked_trie.child(marked_entry_node, token)
        marked_states, marked_ends = nfa.graft_terminals(marked_trie, nfa.new_state())
        complete |= marked_ends
        marked_edges = [(token, marked_states[c]) for token, c in marked_trie.children[0].items()]
        if sub_entry is not None:
            nfa.add_edge(marked_states[marked_entry_node], sub_entry[0], sub_entry[1])

    def wire(state: int, marked: bool) -> None:
        if marked and not marked_edges:  # pragma: no cover - incohérence interne
            raise GrammarDerivationError(
                "Marqueur de reste requis (million) mais chemin marqué non dérivé."
            )
        for token, target in marked_edges if marked else tail_edges:
            nfa.add_edge(state, token, target)

    wire(scale_state, layer.bare_marker)
    for m, node in multiplier_nodes.items():
        wire(multiplier_states[node], layer.multiplier_marker.get(m, False))
    for m_, node in zm_nodes.items():
        wire(zm_states[node], layer.sub_multiplier_marker.get(m_, False))
    for r_, node in ztail_nodes.items():
        wire(ztail_states[node], layer.sub_tail_marker.get(r_, False))

    return complete


def _build_nfa(derived: _Derived) -> tuple[_Nfa, int]:
    nfa = _Nfa()
    start = nfa.new_state()
    nfa.accepting = _graft_number_language(nfa, start, derived)
    return nfa, start


def _build_expression_nfa(
    derived: _Derived,
    operators: Sequence[tuple[str, ...]],
    *,
    accept_bare_number: bool = False,
) -> tuple[_Nfa, int]:
    """NFA de ``EXPRESSION := NOMBRE OPÉRATEUR NOMBRE`` (story 6.1, task 2).

    La grammaire des nombres n'est **pas réécrite** : elle est greffée deux fois
    à l'identique, reliée par les mots d'opérateur — une chaîne par **surface**
    (canonique ou variante, cf. ``_operator_surfaces``). Seuls les états de fin
    du **second** opérande sont acceptants — un nombre seul, ou un nombre suivi
    d'un opérateur, ne termine pas un énoncé valide.
    """
    nfa = _Nfa()
    start = nfa.new_state()
    left_complete = _graft_number_language(nfa, start, derived)

    right_root = nfa.new_state()
    right_complete = _graft_number_language(nfa, right_root, derived)

    for tokens in operators:
        # Chaîne de l'opérateur construite à rebours depuis l'opérande droit :
        # elle est partagée par tous les états de fin de l'opérande gauche.
        node = right_root
        for token in reversed(tokens[1:]):
            previous = nfa.new_state()
            nfa.add_edge(previous, token, node)
            node = previous
        for state in left_complete:
            nfa.add_edge(state, tokens[0], node)

    # ``accept_bare_number`` ajoute les états de fin du **premier** opérande aux
    # états acceptants : la langue devient « un nombre seul OU une opération ».
    # C'est ce dont la calculatrice a besoin — l'utilisateur dicte tantôt un
    # montant, tantôt un calcul, et le décodeur ne charge qu'une langue à la
    # fois. Aucune ambiguïté n'en découle : l'alphabet des opérateurs est
    # disjoint de celui des nombres (vérifié par `_operator_surfaces`), donc
    # aucune suite de mots n'est lisible des deux façons.
    nfa.accepting = (right_complete | left_complete) if accept_bare_number else right_complete
    return nfa, start


def _determinize(nfa: _Nfa, start: int) -> tuple[list[dict[str, int]], set[int], int]:
    """Construction par sous-ensembles ; retourne (transitions, accepting, start)."""
    start_set = frozenset({start})
    index: dict[frozenset[int], int] = {start_set: 0}
    transitions: list[dict[str, int]] = [{}]
    accepting: set[int] = set()
    queue = [start_set]

    while queue:
        current = queue.pop()
        current_id = index[current]
        if any(state in nfa.accepting for state in current):
            accepting.add(current_id)
        moves: dict[str, set[int]] = {}
        for state in current:
            for token, targets in nfa.transitions[state].items():
                moves.setdefault(token, set()).update(targets)
        for token, targets in moves.items():
            key = frozenset(targets)
            target_id = index.get(key)
            if target_id is None:
                target_id = len(transitions)
                index[key] = target_id
                transitions.append({})
                queue.append(key)
            transitions[current_id][token] = target_id

    return transitions, accepting, 0


def _minimize(
    transitions: list[dict[str, int]], accepting: set[int], start: int
) -> tuple[list[dict[str, int]], set[int], int]:
    """Minimise un DFA **acyclique** (la langue est finie, l'automate est un DAG).

    Parcours en ordre topologique inverse : deux états sont fusionnés dès que
    leur signature — (acceptant ?, transitions vers des représentants déjà
    minimisés) — coïncide, c'est-à-dire dès qu'ils reconnaissent le même langage
    résiduel. Les suffixes communs aux différentes branches (queues de reste,
    fins de formes) deviennent ainsi physiquement partagés.
    """
    order: list[int] = []
    seen = {start}
    stack: list[tuple[int, list[int]]] = [(start, list(transitions[start].values()))]
    while stack:
        state, pending = stack[-1]
        if pending:
            nxt = pending.pop()
            if nxt not in seen:
                seen.add(nxt)
                stack.append((nxt, list(transitions[nxt].values())))
        else:
            order.append(state)
            stack.pop()

    representative: dict[int, int] = {}
    by_signature: dict[tuple[bool, tuple[tuple[str, int], ...]], int] = {}
    minimized: list[dict[str, int]] = []
    minimized_accepting: set[int] = set()
    for state in order:  # enfants d'abord : leurs représentants sont connus
        remapped = {token: representative[dst] for token, dst in transitions[state].items()}
        signature = (state in accepting, tuple(sorted(remapped.items())))
        found = by_signature.get(signature)
        if found is None:
            found = len(minimized)
            by_signature[signature] = found
            minimized.append(remapped)
            if state in accepting:
                minimized_accepting.add(found)
        representative[state] = found

    return minimized, minimized_accepting, representative[start]


# ---------------------------------------------------------------------------
# Prononciations alternatives (variantes LINGUISTIQUES uniquement — FR8)
# ---------------------------------------------------------------------------


def _canonical_token_forms(lex: Lexicon) -> set[str]:
    """Toutes les formes canoniques du lexique — jamais réinterprétées."""
    forms: set[str] = {lex.zero.canonical}
    for unit in lex.units.values():
        forms.add(unit.isolated)
        forms.add(unit.combined)
    for term in lex.tens.values():
        if term.canonical:
            forms.add(term.canonical)
    for term in lex.connectors.values():
        if term.canonical:
            forms.add(term.canonical)
    for scale in lex.scales.values():
        if scale.canonical:
            forms.add(scale.canonical)
    for operator in lex.operators.values():
        if operator.canonical:
            forms.update(operator.canonical.split())
    return forms


def _build_pronunciations(lex: Lexicon, alphabet: frozenset[str]) -> dict[str, tuple[str, ...]]:
    """Token canonique -> prononciations alternatives (canonique incluse).

    C'est le mécanisme qui remplace, en amont, la table de variantes en aval :
    plusieurs orthographes entendues mènent au **même** token canonique, donc à
    la même forme de sortie. Les ``asr_confusions`` du lexique ne sont
    volontairement **jamais** lues ici (structures distinctes, FR8).

    Deux protections :

    - une variante qui est elle-même une forme canonique (``fo`` face à
      ``afo``) **ou un token de surface de l'automate** (``wey``, forme élidée
      émise après ``di``, listée comme variante de ``iwey``) n'est pas
      réécrite — elle garde son sens contextuel ;
    - une variante multi-tokens (segmentation, ``i wey`` face à ``iwey``) n'a
      pas de place dans un mapping token-à-token ; elle relève du décodeur
      (story 5.6 task 2) et est ignorée ici.
    """
    protected = _canonical_token_forms(lex) | alphabet
    alternatives: dict[str, set[str]] = {token: {token} for token in alphabet}
    owner: dict[str, str] = {token: token for token in alphabet}

    def register(canonical: str | None, variants: Iterable[str]) -> None:
        if canonical is None or canonical not in alternatives:
            return
        for variant in variants:
            if variant == canonical or variant in protected or " " in variant:
                continue
            previous = owner.get(variant)
            if previous is not None and previous != canonical:
                raise GrammarDerivationError(
                    f"Prononciation ambiguë : {variant!r} renvoie à la fois vers "
                    f"{previous!r} et {canonical!r}."
                )
            owner[variant] = canonical
            alternatives[canonical].add(variant)

    register(lex.zero.canonical, lex.zero.variants)
    for unit in lex.units.values():
        register(unit.isolated, unit.variants)
        register(unit.combined, unit.variants)
    for term in lex.tens.values():
        register(term.canonical, term.variants)
    for term in lex.connectors.values():
        register(term.canonical, term.variants)
    for scale in lex.scales.values():
        register(scale.canonical, scale.variants)
    for operator in lex.operators.values():
        register(operator.canonical, operator.variants)

    return {token: tuple(sorted(forms)) for token, forms in alternatives.items()}


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class NumberGrammar:
    """Automate fini déterministe des formes numériques zarma valides.

    Toute chaîne acceptée est, par construction, une forme produite par
    ``generate`` — donc parseable par ``parse`` et re-générable à l'identique.
    L'automate est **acyclique** (langue finie) : un parcours consomme au plus
    ``max_length`` tokens.
    """

    grammar_version: str
    start: int
    accepting_states: frozenset[int]
    tokens: frozenset[str]
    pronunciations: Mapping[str, tuple[str, ...]]
    _transitions: tuple[Mapping[str, int], ...]
    _canonical_by_spelling: Mapping[str, str]
    #: Langue décrite : ``"numbers"`` (5.6) ou ``"expressions"`` (6.1). Même
    #: structure, même interface — c'est ce qui permet au décodeur contraint de
    #: changer de langue sans changer d'algorithme.
    kind: str = "numbers"
    #: Mots d'opérateur présents dans l'automate (vide pour ``"numbers"``).
    operator_tokens: frozenset[str] = frozenset()
    #: Surface d'opérateur variante -> surface **canonique** (celle que la
    #: banque vocale sait prononcer). C'est le pendant, au niveau des
    #: **séquences**, de la table ``pronunciations`` token-à-token : une
    #: variante multi-tokens (« kanga itonton ») ne peut pas converger token
    #: par token, elle converge ici, dans ``canonical_form()``.
    _operator_rewrites: Mapping[tuple[str, ...], tuple[str, ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )

    # --- structure ---

    @property
    def state_count(self) -> int:
        return len(self._transitions)

    def transitions(self, state: int) -> Mapping[str, int]:
        """Transitions sortantes de ``state`` (token canonique -> état)."""
        return self._transitions[state]

    def next_tokens(self, state: int) -> frozenset[str]:
        """Tokens canoniques autorisés depuis ``state`` (contrainte du faisceau)."""
        return frozenset(self._transitions[state])

    def is_accepting(self, state: int) -> bool:
        return state in self.accepting_states

    # --- parcours ---

    def canonical_token(self, spelling: str) -> str | None:
        """Token canonique d'une prononciation, ou ``None`` si inconnue."""
        return self._canonical_by_spelling.get(spelling)

    def step(self, state: int, token: str, *, allow_pronunciations: bool = True) -> int | None:
        """Consomme ``token`` depuis ``state``. ``None`` si la transition n'existe pas.

        Aucune approximation : la seule tolérance est la table de prononciations
        (variantes linguistiques), jamais une distance textuelle.
        """
        edges = self._transitions[state]
        target = edges.get(token)
        if target is None and allow_pronunciations:
            canonical = self._canonical_by_spelling.get(token)
            if canonical is not None:
                target = edges.get(canonical)
        return target

    def walk(
        self, tokens: Iterable[str], *, allow_pronunciations: bool = True
    ) -> tuple[int | None, list[str]]:
        """Parcourt ``tokens`` ; retourne (état final ou ``None``, tokens canoniques)."""
        state: int | None = self.start
        canonical: list[str] = []
        for token in tokens:
            if state is None:
                return None, canonical
            target = self.step(state, token, allow_pronunciations=allow_pronunciations)
            if target is None:
                return None, canonical
            canonical.append(
                token if token in self._transitions[state] else self._canonical_by_spelling[token]
            )
            state = target
        return state, canonical

    def accepts(
        self, text_or_tokens: str | Iterable[str], *, allow_pronunciations: bool = True
    ) -> bool:
        """La séquence appartient-elle à la grammaire des nombres ?"""
        state, _ = self.walk(_as_tokens(text_or_tokens), allow_pronunciations=allow_pronunciations)
        return state is not None and self.is_accepting(state)

    def canonical_form(
        self, text_or_tokens: str | Iterable[str], *, allow_pronunciations: bool = True
    ) -> str | None:
        """Forme canonique de la séquence, ou ``None`` si elle n'est pas valide.

        C'est ici que les prononciations alternatives convergent : toutes celles
        d'un même token produisent la **même** chaîne canonique. Les surfaces
        d'opérateur variantes (y compris multi-tokens, « kanga itonton »)
        convergent de même vers leur surface canonique (``tonton``) — la seule
        que la banque vocale sait prononcer.
        """
        state, canonical = self.walk(
            _as_tokens(text_or_tokens), allow_pronunciations=allow_pronunciations
        )
        if state is None or not self.is_accepting(state):
            return None
        return " ".join(self._rewrite_operator_surface(canonical))

    def _rewrite_operator_surface(self, tokens: list[str]) -> list[str]:
        """Ramène la plage d'opérateur de ``tokens`` à sa surface canonique.

        Les mots d'opérateur étant disjoints de ceux des nombres, une séquence
        acceptée en contient au plus une plage contiguë, et cette plage est
        exactement l'une des surfaces déclarées : la réécriture est univoque.
        Sans opérateur (grammaire des nombres) ou sur une surface déjà
        canonique, la séquence est retournée telle quelle.
        """
        if not self._operator_rewrites:
            return tokens
        start = 0
        while start < len(tokens) and tokens[start] not in self.operator_tokens:
            start += 1
        end = start
        while end < len(tokens) and tokens[end] in self.operator_tokens:
            end += 1
        if start == end:
            return tokens
        canonical = self._operator_rewrites.get(tuple(tokens[start:end]))
        if canonical is None:
            return tokens
        return tokens[:start] + list(canonical) + tokens[end:]


def _as_tokens(text_or_tokens: str | Iterable[str]) -> tuple[str, ...]:
    if isinstance(text_or_tokens, str):
        return _tokens(text_or_tokens)
    return tuple(text_or_tokens)


def _finalize(
    lex: Lexicon,
    nfa: _Nfa,
    start: int,
    *,
    kind: str,
    operator_tokens: frozenset[str] = frozenset(),
    operator_rewrites: Mapping[tuple[str, ...], tuple[str, ...]] | None = None,
) -> NumberGrammar:
    """Déterminise, minimise, construit la table de prononciations et emballe le DFA."""
    transitions, accepting, dfa_start = _determinize(nfa, start)
    transitions, accepting, dfa_start = _minimize(transitions, accepting, dfa_start)

    alphabet = frozenset(token for edges in transitions for token in edges)
    pronunciations = _build_pronunciations(lex, alphabet)
    canonical_by_spelling = {
        spelling: canonical
        for canonical, spellings in pronunciations.items()
        for spelling in spellings
    }

    return NumberGrammar(
        grammar_version=lex.grammar_version,
        start=dfa_start,
        accepting_states=frozenset(accepting),
        tokens=alphabet,
        pronunciations=MappingProxyType(pronunciations),
        _transitions=tuple(MappingProxyType(dict(edges)) for edges in transitions),
        _canonical_by_spelling=MappingProxyType(canonical_by_spelling),
        kind=kind,
        operator_tokens=operator_tokens,
        _operator_rewrites=MappingProxyType(dict(operator_rewrites or {})),
    )


def build_grammar(lexicon: Lexicon | None = None) -> NumberGrammar:
    """Construit la grammaire à partir du lexique et du **générateur** (source unique)."""
    lex = lexicon if lexicon is not None else load_lexicon()
    derived = _derive_forms(lex)
    nfa, start = _build_nfa(derived)
    return _finalize(lex, nfa, start, kind="numbers")


def _operator_surfaces(
    lex: Lexicon, number_alphabet: frozenset[str]
) -> list[tuple[tuple[str, ...], tuple[str, ...]]]:
    """Surfaces d'opérateur **résolues** — paires ``(surface, surface canonique)``.

    Chaque opérateur contribue sa forme canonique **et ses variantes**
    (``variants`` du lexique) : les variantes multi-tokens (« kanga itonton »)
    ne peuvent pas passer par la table de prononciations token-à-token, elles
    sont donc des chemins à part entière de l'automate. La convergence
    entrée → sortie est portée par la paire : toute surface acceptée se ramène
    à sa surface **canonique** dans ``canonical_form()`` — c'est elle que la
    banque vocale sait prononcer.

    C'est ici que se joue le risque identifié par la story : la composition des
    nombres utilise déjà des connecteurs (``da`` / ``di`` / ``cindi``). Si un mot
    d'opérateur en était un, une même suite de mots serait à la fois *un nombre*
    et *une opération*, et le décodage contraint n'aurait plus de chemin unique.

    Le contrôle n'est pas une supposition, c'est une **vérification mécanique**
    à chaque construction : l'alphabet des opérateurs — surfaces canoniques
    **et** variantes — doit être disjoint de celui des nombres, sinon
    ``GrammarDerivationError``. La disjonction suffit à établir la non-ambiguïté
    de la langue des expressions :

    1. un mot d'opérateur ne peut apparaître dans aucun nombre, donc toute
       expression acceptée contient **exactement une** plage contiguë de mots
       d'opérateur — la découpe ``gauche | opérateur | droite`` est unique, et
       la plage est exactement l'une des surfaces déclarées (le lexique refuse
       qu'une même forme serve deux opérateurs) ;
    2. chaque côté est un nombre, et la langue des nombres est elle-même
       univoque sur la plage résolue (invariant ``parse(generate(n)) == n``).

    Une expression acceptée a donc une seule lecture. La déterminisation, elle,
    ne fait que rendre le parcours efficace : elle n'apporte pas cette propriété.
    """
    surfaces: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    for name in sorted(lex.operators):
        operator = lex.operators[name]
        if operator.canonical is None:
            continue  # forme non validée par un locuteur : absente, jamais devinée
        canonical = tuple(operator.canonical.split())
        if not canonical:
            raise GrammarDerivationError(f"Opérateur '{name}' : forme canonique vide.")
        seen: set[tuple[str, ...]] = set()
        for form in (operator.canonical, *operator.variants):
            tokens = tuple(form.split())
            if not tokens:
                raise GrammarDerivationError(f"Opérateur '{name}' : forme vide.")
            if tokens in seen:
                continue
            seen.add(tokens)
            collisions = sorted(set(tokens) & number_alphabet)
            if collisions:
                raise GrammarDerivationError(
                    f"Opérateur '{name}' ambigu : {collisions} appartient déjà à la "
                    "grammaire des nombres. Une même suite de mots serait lisible "
                    "comme un nombre et comme une opération."
                )
            surfaces.append((tokens, canonical))
    return surfaces


def build_calculator_grammar(lexicon: Lexicon | None = None) -> NumberGrammar:
    """Automate de ``NOMBRE | NOMBRE OPÉRATEUR NOMBRE`` — la langue réellement
    parlée à la calculatrice.

    Le décodeur contraint ne charge qu'une grammaire à la fois. Avec
    ``expressions``, un utilisateur qui dicte simplement « zangou » obtient un
    rejet ; avec ``numbers``, aucun calcul n'est reconnu. Or l'application
    attend les deux — un montant *ou* une opération —, et c'est cette union
    qu'il lui faut.

    Constatée en production : le service tournait en ``expressions`` et ne
    reconnaissait donc aucun nombre isolé.
    """
    return build_expression_grammar(lexicon, accept_bare_number=True)


def build_expression_grammar(
    lexicon: Lexicon | None = None, *, accept_bare_number: bool = False
) -> NumberGrammar:
    """Automate de ``NOMBRE OPÉRATEUR NOMBRE`` (story 6.1, task 2).

    Même type, même interface que ``build_grammar`` — le décodeur contraint de
    la story 5.6 change donc de **langue**, pas d'algorithme.

    Les opérateurs non résolus au lexique (``canonical: null``) sont simplement
    absents : la grammaire décrit alors les seules opérations réellement
    attestées. Si **aucun** opérateur n'est résolu, la construction échoue
    (``GrammarDerivationError``) plutôt que de produire un automate vide qui
    n'accepterait rien en silence.
    """
    lex = lexicon if lexicon is not None else load_lexicon()
    derived = _derive_forms(lex)

    number_nfa, number_start = _build_nfa(derived)
    number_alphabet = frozenset(token for edges in number_nfa.transitions for token in edges)
    surfaces = _operator_surfaces(lex, number_alphabet)
    if not surfaces:
        raise GrammarDerivationError(
            "Aucun opérateur résolu dans le lexique : la grammaire des "
            "expressions n'accepterait rien. Compléter `operators` "
            "(cf. docs/lexique-operateurs-a-valider.md)."
        )
    del number_nfa, number_start  # n'a servi qu'à observer l'alphabet des nombres

    nfa, start = _build_expression_nfa(
        derived,
        [surface for surface, _ in surfaces],
        accept_bare_number=accept_bare_number,
    )
    operator_tokens = frozenset(token for surface, _ in surfaces for token in surface)
    operator_rewrites = {
        surface: canonical for surface, canonical in surfaces if surface != canonical
    }
    return _finalize(
        lex,
        nfa,
        start,
        kind="calculator" if accept_bare_number else "expressions",
        operator_tokens=operator_tokens,
        operator_rewrites=operator_rewrites,
    )


@lru_cache(maxsize=1)
def load_grammar() -> NumberGrammar:
    """Grammaire du lexique embarqué, construite une seule fois (coûteuse à bâtir)."""
    return build_grammar()


@lru_cache(maxsize=1)
def load_expression_grammar() -> NumberGrammar:
    """Grammaire des expressions du lexique embarqué (construite une seule fois)."""
    return build_expression_grammar()


@lru_cache(maxsize=1)
def load_calculator_grammar() -> NumberGrammar:
    """Union « nombre seul OU opération » — la langue de la calculatrice."""
    return build_calculator_grammar()


__all__ = [
    "NumberGrammar",
    "build_grammar",
    "build_expression_grammar",
    "build_calculator_grammar",
    "load_grammar",
    "load_expression_grammar",
    "load_calculator_grammar",
]
