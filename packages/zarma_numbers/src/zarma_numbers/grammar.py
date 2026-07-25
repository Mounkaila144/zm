"""Grammaire des formes valides, exploitable par un décodeur (story 5.6, task 1).

Ce module expose **la langue exacte du générateur** — l'ensemble des chaînes
``generate(n)`` pour ``n`` dans ``[0, 1 000 000]`` — sous la forme d'un
**automate fini déterministe** (DFA) sur des séquences de tokens. C'est la
structure que consomme une recherche en faisceau contrainte : à chaque état,
``next_tokens()`` donne les continuations autorisées, sans jamais énumérer
l'espace des 1 000 001 formes.

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

Construction (deux étapes classiques) :

1. Un **NFA** est assemblé à partir de tries observés (formes autonomes
   ``0..999``, multiplicateurs de milliers, queues de reste, restes marqués).
   Depuis la correction locuteur (lexique 1.2.0), le connecteur de groupes est
   en distribution complémentaire (``da``/``di``) et ses continuations en
   dépendent : les queues de reste sont donc observées **connecteur inclus**
   (``('da', 'fo')``, ``('di', 'wey')``…) et c'est le trie des queues lui-même
   qui encode la dépendance connecteur → continuations. Le non-déterminisme
   reste réel : après ``zambar zangou yega da``, on peut être encore dans le
   multiplicateur (``zambar zangou yega da wayyegga`` = 990 milliers) *ou* sur
   le chemin du marqueur (``zambar zangou yega da dala fo`` = 900 001).
2. Une **déterminisation par sous-ensembles** produit le DFA public. La langue
   étant finie, le DFA est acyclique.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from types import MappingProxyType

from .exceptions import GrammarDerivationError, UnresolvedFormError
from .generator import MAX_VALUE, generate
from .loader import Lexicon, load_lexicon

#: Bornes des sous-langues observées sur le générateur (dérivées, pas décrétées :
#: ce sont les plages sur lesquelles on interroge ``generate``).
_BELOW_1000_MAX = 999
_THOUSAND_STEP = 1000

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
class _Derived:
    """Sous-langues observées sur ``generate()``."""

    #: n -> forme, pour les nombres qui ne passent pas par l'échelle « millier ».
    standalone: dict[int, tuple[str, ...]]
    #: Forme du million (cas lexical particulier), si résolue.
    million: tuple[str, ...] | None
    #: Tokens de l'échelle « millier » (préfixe du groupe des milliers).
    thousand: tuple[str, ...]
    #: m -> forme du multiplicateur de milliers (1..999).
    multipliers: dict[int, tuple[str, ...]]
    #: r -> queue observée après <millier> <mult(1)>, **connecteur inclus**
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


def _derive_forms(lex: Lexicon) -> _Derived:
    """Dérive les sous-langues **en observant** ``generate()``.

    Rien n'est décrété ici : chaque forme provient d'un appel au générateur, et
    chaque découpage est vérifié (préfixe attendu), sans quoi on échoue. Le
    choix ``da``/``di`` du connecteur n'est jamais recalculé : il est **lu** en
    tête de chaque queue de reste observée.
    """
    standalone: dict[int, tuple[str, ...]] = {}
    for n in range(0, _BELOW_1000_MAX + 1):
        form = _safe_generate(n)
        if form is not None:
            standalone[n] = form

    million = _safe_generate(MAX_VALUE)

    # Formes du connecteur de groupes (distribution complémentaire da/di) :
    # seules têtes de queue admissibles — tout autre découpage est une erreur.
    connector_forms: set[str] = set()
    for key in ("groups", "groups_elided"):
        term = lex.connectors.get(key)
        if term is not None and term.canonical is not None:
            connector_forms.add(term.canonical)
    if not connector_forms:
        raise GrammarDerivationError("Connecteur de groupes non résolu : grammaire indérivable.")

    thousand_scale = lex.scales["thousand"].canonical
    base = _safe_generate(_THOUSAND_STEP)
    if thousand_scale is None or base is None:
        # Échelle « millier » non résolue : la grammaire se limite à 0..999.
        return _Derived(
            standalone=standalone,
            million=million,
            thousand=(),
            multipliers={},
            remainder_tails={},
            marker_required={},
            marker_prefix=None,
            marker_remainders={},
        )
    thousand = _tokens(thousand_scale)

    # Multiplicateurs : generate(m * 1000) = <millier> <multiplicateur(m)>.
    multipliers: dict[int, tuple[str, ...]] = {}
    for m in range(1, _BELOW_1000_MAX + 1):
        form = _safe_generate(m * _THOUSAND_STEP)
        if form is None:
            continue
        multipliers[m] = _strip_prefix(form, thousand, f"multiplicateur {m}")

    if 1 not in multipliers:
        raise GrammarDerivationError(
            "Multiplicateur de milliers 1 non résolu : grammaire indérivable."
        )

    # Queues de reste : generate(1000 + r) = <millier> <mult(1)> <queue(r)>.
    # La queue commence par le connecteur que le générateur a choisi pour r —
    # observé, jamais recalculé. Le multiplicateur 1 n'appelle aucun marqueur
    # de reste (recoupé ci-dessous).
    remainder_prefix = thousand + multipliers[1]
    remainder_tails: dict[int, tuple[str, ...]] = {}
    for r in range(1, _BELOW_1000_MAX + 1):
        form = _safe_generate(_THOUSAND_STEP + r)
        if form is None:
            continue
        tail = _strip_prefix(form, remainder_prefix, f"reste {r}")
        if not tail or tail[0] not in connector_forms:
            raise GrammarDerivationError(
                f"Structure inattendue du générateur pour le reste {r} : la queue "
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

    marker_term = lex.connectors.get("remainder")
    marker = marker_term.canonical if marker_term is not None else None

    marker_required: dict[int, bool] = {}
    marker_prefix: tuple[str, ...] | None = None
    marked_probe_tails: dict[tuple[int, int], tuple[str, ...]] = {}
    for m, multiplier in multipliers.items():
        statuses: set[bool] = set()
        for probe in sorted(probes.values()):
            form = _safe_generate(m * _THOUSAND_STEP + probe)
            if form is None:
                continue
            tail = _strip_prefix(form, thousand + multiplier, f"reste du multiplicateur {m}")
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
                        f"Préfixe marqué incohérent pour le multiplicateur {m} : "
                        f"{tail[:2]!r} au lieu de {marker_prefix!r}."
                    )
                statuses.add(True)
                marked_probe_tails[(m, probe)] = tail
                continue
            raise GrammarDerivationError(
                f"Reste inattendu pour le multiplicateur {m} : {tail!r} "
                f"(ni la queue observée {remainder_tails[probe]!r}, "
                f"ni connecteur + marqueur + reste)."
            )
        if len(statuses) > 1:
            raise GrammarDerivationError(
                f"Marqueur de reste incohérent pour le multiplicateur {m} : "
                "requis pour certains restes seulement."
            )
        marker_required[m] = statuses.pop() if statuses else False

    # Chemin marqué : dérivé intégralement sur le premier multiplicateur marqué,
    # puis recoupé avec les sondes des autres multiplicateurs marqués.
    marker_remainders: dict[int, tuple[str, ...]] = {}
    marked = sorted(m for m, required in marker_required.items() if required)
    if marked:
        assert marker_prefix is not None  # garanti par la boucle de détection
        marked_prefix_tokens = thousand + multipliers[marked[0]] + marker_prefix
        for r in range(1, _BELOW_1000_MAX + 1):
            form = _safe_generate(marked[0] * _THOUSAND_STEP + r)
            if form is None:
                continue
            marker_remainders[r] = _strip_prefix(form, marked_prefix_tokens, f"reste marqué {r}")
        # Cohérence : les restes marqués (le connecteur porte sur le marqueur,
        # ni sélection di ni élision) parlent la même sous-langue que les
        # multiplicateurs.
        if set(marker_remainders.values()) != set(multipliers.values()):
            raise GrammarDerivationError(
                "Restes marqués et multiplicateurs ne décrivent pas la même "
                "sous-langue : hypothèse de composition invalidée."
            )
        for (m, probe), tail in marked_probe_tails.items():
            if tail != marker_prefix + marker_remainders[probe]:
                raise GrammarDerivationError(
                    f"Reste marqué inattendu pour le multiplicateur {m} : {tail!r}."
                )

    return _Derived(
        standalone=standalone,
        million=million,
        thousand=thousand,
        multipliers=multipliers,
        remainder_tails=remainder_tails,
        marker_required=marker_required,
        marker_prefix=marker_prefix,
        marker_remainders=marker_remainders,
    )


# ---------------------------------------------------------------------------
# Trie / NFA / déterminisation
# ---------------------------------------------------------------------------


@dataclass
class _Trie:
    """Trie de séquences de tokens (structure de construction, non publique)."""

    children: list[dict[str, int]] = field(default_factory=lambda: [{}])
    terminals: set[int] = field(default_factory=set)

    def insert(self, tokens: Sequence[str]) -> int:
        node = 0
        for token in tokens:
            nxt = self.children[node].get(token)
            if nxt is None:
                self.children.append({})
                nxt = len(self.children) - 1
                self.children[node][token] = nxt
            node = nxt
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
        """Greffe ``trie`` sur l'état ``root`` ; retourne node de trie -> état NFA."""
        mapping = [root] + [self.new_state() for _ in range(len(trie.children) - 1)]
        for node, edges in enumerate(trie.children):
            for token, child in edges.items():
                self.add_edge(mapping[node], token, mapping[child])
        for node in trie.terminals:
            self.accepting.add(mapping[node])
        return mapping


def _build_nfa(derived: _Derived) -> tuple[_Nfa, int]:
    nfa = _Nfa()
    start = nfa.new_state()

    standalone_trie = _Trie()
    for form in derived.standalone.values():
        standalone_trie.insert(form)
    if derived.million is not None:
        standalone_trie.insert(derived.million)
    nfa.graft(standalone_trie, start)

    if not derived.multipliers:
        return nfa, start

    # Branche des milliers : <millier> <multiplicateur> [ <queue(r)> ], où la
    # queue observée inclut son connecteur (``da …`` / ``di …``), ou, pour les
    # multiplicateurs marqués, <connecteur> <marqueur> <reste plein>.
    multiplier_trie = _Trie()
    multiplier_nodes = {
        m: multiplier_trie.insert(derived.thousand + form)
        for m, form in derived.multipliers.items()
    }
    multiplier_states = nfa.graft(multiplier_trie, start)

    def entry_edges(trie: _Trie) -> list[tuple[str, int]]:
        """Greffe ``trie`` sur un état neuf ; retourne ses arêtes racine.

        Recopier ces arêtes sur chaque état de fin de multiplicateur équivaut à
        une ε-transition vers la racine du trie : le connecteur est la première
        arête du trie, donc ses continuations en dépendent par construction.
        """
        states = nfa.graft(trie, nfa.new_state())
        return [(token, states[child]) for token, child in trie.children[0].items()]

    tail_trie = _Trie()
    for tail in derived.remainder_tails.values():
        tail_trie.insert(tail)
    tail_edges = entry_edges(tail_trie)

    marked_edges: list[tuple[str, int]] = []
    if derived.marker_prefix is not None:
        marked_trie = _Trie()
        for form in derived.marker_remainders.values():
            marked_trie.insert(derived.marker_prefix + form)
        marked_edges = entry_edges(marked_trie)

    for m, node in multiplier_nodes.items():
        required = derived.marker_required.get(m, False)
        if required and not marked_edges:  # pragma: no cover - incohérence interne
            raise GrammarDerivationError(f"Marqueur de reste requis pour {m} mais non résolu.")
        for token, target in marked_edges if required else tail_edges:
            nfa.add_edge(multiplier_states[node], token, target)

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
        d'un même token produisent la **même** chaîne canonique.
        """
        state, canonical = self.walk(
            _as_tokens(text_or_tokens), allow_pronunciations=allow_pronunciations
        )
        if state is None or not self.is_accepting(state):
            return None
        return " ".join(canonical)


def _as_tokens(text_or_tokens: str | Iterable[str]) -> tuple[str, ...]:
    if isinstance(text_or_tokens, str):
        return _tokens(text_or_tokens)
    return tuple(text_or_tokens)


def build_grammar(lexicon: Lexicon | None = None) -> NumberGrammar:
    """Construit la grammaire à partir du lexique et du **générateur** (source unique)."""
    lex = lexicon if lexicon is not None else load_lexicon()
    derived = _derive_forms(lex)
    nfa, start = _build_nfa(derived)
    transitions, accepting, dfa_start = _determinize(nfa, start)

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
    )


@lru_cache(maxsize=1)
def load_grammar() -> NumberGrammar:
    """Grammaire du lexique embarqué, construite une seule fois (coûteuse à bâtir)."""
    return build_grammar()


__all__ = ["NumberGrammar", "build_grammar", "load_grammar"]
