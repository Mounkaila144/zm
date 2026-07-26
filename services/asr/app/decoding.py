"""Décodage CTC contraint à la grammaire des nombres zarma (story 5.6, task 2).

Recherche en faisceau par préfixes (*prefix beam search*) sur les logits CTC,
restreinte à l'automate de ``zarma_numbers.grammar`` (task 1). L'espace
0–1 000 000 est couvert **sans énumération de candidats** : la contrainte est
appliquée transition par transition pendant la recherche.

Module volontairement **auto-contenu** : numpy + ``zarma_numbers`` + stdlib
uniquement — ni torch, ni modal, ni fairseq2. Il est donc :

- importable dans l'image Modal (``services/asr/app/main.py``, task 4) où les
  logits sont produits par le modèle CTC ;
- testable en CI **sans GPU ni modèle**, sur des logits en fixtures
  (``services/asr/tests``, chargé par ``importlib`` pour éviter la collision de
  nom avec le paquet ``app`` de ``services/api``).

Scoring (validé empiriquement, Annexe A §3 de la story) :

    score = ctc_nll(candidat) / len(candidat_ids) ** p        (plus bas = mieux)

avec ``p = 1.0`` par défaut (optimum mesuré) et ``blank = 0`` (Annexe D §1 :
``blank = 1`` a été testé et s'effondre). Sans normalisation par la longueur,
le biais du CTC vers les séquences courtes fait tout converger vers ``afo``.

Contrainte de durée (mode d'échec A.5 : énoncés courts appariés à des candidats
longs) : chaque token restant à émettre exige au moins ``min_frames_per_token``
trames. C'est un principe **acoustique** (une trame ≈ 20 ms ne peut pas porter
plusieurs caractères), pas du fuzzy matching : à ``1.0`` c'est exactement la
faisabilité CTC ; au-delà, les candidats trop longs pour l'audio sont élagués.

Aucun paramètre n'est codé en dur dans la logique : tout passe par
``DecoderConfig`` (branché sur ``Settings`` en task 7).
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
from zarma_numbers.grammar import NumberGrammar

# ---------------------------------------------------------------------------
# Lexique de décodage : mot de la grammaire -> séquences d'ids du tokenizer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenLexicon:
    """Encodages tokenizer des mots de la grammaire.

    ``entries`` associe chaque mot **canonique** de la grammaire aux séquences
    d'ids de *toutes* ses orthographes (canonique + prononciations alternatives
    de la task 1) : plusieurs encodages mènent au même mot émis — c'est le
    mécanisme de convergence des variantes, sans aucune correction en aval.

    ``separator`` est la séquence d'ids séparant deux mots (l'espace pour le
    tokenizer Omnilingual) ; vide si le tokenizer n'en émet pas.
    """

    entries: Mapping[str, tuple[tuple[int, ...], ...]]
    separator: tuple[int, ...] = ()


def build_token_lexicon(
    grammar: NumberGrammar,
    encode: Callable[[str], Sequence[int]],
    *,
    separator: Sequence[int] = (),
    blank_id: int = 0,
    include_pronunciations: bool = True,
) -> TokenLexicon:
    """Construit le lexique de décodage en encodant chaque orthographe.

    ``encode`` est l'encodeur du tokenizer réel (côté service ASR) ou un
    encodeur de test (CI). Les ids doivent être filtrés des tokens spéciaux en
    amont si nécessaire (cf. Annexe A §2 : garder les ids ``> 3``).

    :raises ValueError: si une orthographe s'encode vide ou contient ``blank``
        (le blank n'est jamais une étiquette CTC).
    """
    entries: dict[str, tuple[tuple[int, ...], ...]] = {}
    for word in sorted(grammar.tokens):
        spellings = grammar.pronunciations[word] if include_pronunciations else (word,)
        encoded: list[tuple[int, ...]] = []
        for spelling in spellings:
            ids = tuple(int(i) for i in encode(spelling))
            if not ids:
                raise ValueError(f"L'orthographe {spelling!r} s'encode en séquence vide.")
            if blank_id in ids:
                raise ValueError(
                    f"L'orthographe {spelling!r} contient l'id blank ({blank_id}) : "
                    "encodage inutilisable pour le CTC."
                )
            if ids not in encoded:
                encoded.append(ids)
        entries[word] = tuple(encoded)
    sep = tuple(int(i) for i in separator)
    if blank_id in sep:
        raise ValueError(f"Le séparateur contient l'id blank ({blank_id}).")
    return TokenLexicon(entries=entries, separator=sep)


# ---------------------------------------------------------------------------
# Automate au niveau token-id : grammaire (mots) × lexique (ids)
# ---------------------------------------------------------------------------


@dataclass
class _TokenAutomaton:
    """Automate compilé : arcs (token_id, nœud suivant, mot émis ou None).

    Les nœuds « frontière » correspondent aux états de la grammaire (entre deux
    mots) ; les nœuds internes déroulent les encodages. Le mot canonique est
    émis sur le **dernier** arc de son encodage. L'automate est acyclique.
    """

    arcs: list[list[tuple[int, int, str | None]]] = field(default_factory=list)
    accepting: set[int] = field(default_factory=set)
    start: int = 0
    #: Nombre minimal de tokens restant à émettre pour atteindre l'acceptation
    #: (∞ si aucun chemin) — support de la contrainte de durée.
    min_tokens: list[float] = field(default_factory=list)
    #: Ids tokenizer réellement atteignables, blank compris, triés.
    #:
    #: La grammaire n'emploie que **21 ids distincts** sur les 10 288 du
    #: tokenizer. Tout le décodage peut donc travailler sur une matrice
    #: ``(T, 22)`` au lieu de ``(T, 10 288)`` : 470 fois moins de colonnes à
    #: parcourir, et une ligne de trame qui tient dans le cache L1 au lieu d'un
    #: bloc de 80 Ko qui l'évince à chaque trame.
    used_ids: tuple[int, ...] = ()
    #: ``token_id -> indice de colonne`` dans la matrice compacte.
    col_of: dict[int, int] = field(default_factory=dict)
    #: Arcs pré-résolus pour la boucle chaude :
    #: ``(token_id, colonne, nœud suivant, mot émis, trames minimales requises)``.
    #: Pré-calculer la colonne et le seuil de durée évite, à chaque trame et pour
    #: chaque faisceau, une recherche de dictionnaire et une multiplication.
    fast_arcs: list[tuple[tuple[int, int, int, str | None, float], ...]] = field(
        default_factory=list
    )

    def new_node(self) -> int:
        self.arcs.append([])
        return len(self.arcs) - 1

    def finalize(self, *, blank_id: int, min_frames_per_token: float) -> None:
        """Calcule le sous-vocabulaire utile et pré-résout les arcs."""
        used = {blank_id}
        for node_arcs in self.arcs:
            for token_id, _, _ in node_arcs:
                used.add(token_id)
        self.used_ids = tuple(sorted(used))
        self.col_of = {token_id: col for col, token_id in enumerate(self.used_ids)}
        self.fast_arcs = [
            tuple(
                (
                    token_id,
                    self.col_of[token_id],
                    next_node,
                    emitted,
                    self.min_tokens[next_node] * min_frames_per_token,
                )
                for token_id, next_node, emitted in node_arcs
            )
            for node_arcs in self.arcs
        ]


def _compile_automaton(grammar: NumberGrammar, lexicon: TokenLexicon) -> _TokenAutomaton:
    aut = _TokenAutomaton()
    boundary: dict[int, int] = {}

    def boundary_node(state: int) -> int:
        node = boundary.get(state)
        if node is None:
            node = aut.new_node()
            boundary[state] = node
            if grammar.is_accepting(state):
                aut.accepting.add(node)
        return node

    aut.start = boundary_node(grammar.start)

    # Parcours des états de grammaire atteignables ; pour chaque arête (mot),
    # on greffe une chaîne d'ids par orthographe. Après le premier mot, chaque
    # chaîne est préfixée du séparateur (l'état initial n'est jamais ré-entré :
    # l'automate de la task 1 est acyclique).
    stack = [grammar.start]
    seen = {grammar.start}
    while stack:
        state = stack.pop()
        src = boundary_node(state)
        with_separator = state != grammar.start
        for word, target_state in grammar.transitions(state).items():
            dst = boundary_node(target_state)
            if target_state not in seen:
                seen.add(target_state)
                stack.append(target_state)
            for ids in lexicon.entries[word]:
                chain = (lexicon.separator if with_separator else ()) + ids
                node = src
                for position, token_id in enumerate(chain):
                    last = position == len(chain) - 1
                    emitted = word if last else None
                    nxt = dst if last else aut.new_node()
                    aut.arcs[node].append((token_id, nxt, emitted))
                    node = nxt

    # min_tokens par DFS mémoïsé (DAG ; profondeur ≈ longueur de la plus longue
    # forme en tokens, largement sous la limite de récursion).
    aut.min_tokens = [math.inf] * len(aut.arcs)
    memo: dict[int, float] = {}

    def min_tokens(node: int) -> float:
        cached = memo.get(node)
        if cached is not None:
            return cached
        best = 0.0 if node in aut.accepting else math.inf
        memo[node] = best  # coupe-cycle défensif (l'automate est acyclique)
        for _, nxt, _ in aut.arcs[node]:
            best = min(best, 1.0 + min_tokens(nxt))
        memo[node] = best
        return best

    for node in range(len(aut.arcs)):
        aut.min_tokens[node] = min_tokens(node)
    return aut


# ---------------------------------------------------------------------------
# Configuration et résultats
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DecoderConfig:
    """Paramètres du décodeur — aucun n'est codé en dur dans la logique.

    Défauts = valeurs validées par le prototype (Annexe A §3, Annexe D §1).
    Ils seront exposés via ``Settings`` en task 7.
    """

    #: Largeur du faisceau (nombre de préfixes conservés par trame).
    #: 256 = le plus large faisceau dont la latence de décodage p95 reste très
    #: en dessous de l'inférence du modèle (~218 ms mesurés contre ~600 ms).
    #: Critère de choix **sans étiquettes** : un faisceau plus large ne change
    #: pas la fonction de score, il réduit seulement les échecs de recherche.
    beam_width: int = 256
    #: Nombre d'hypothèses retournées (alimente ``AsrResult.candidates``).
    nbest: int = 5
    #: Id du token blank CTC — 0 pour Omnilingual (PAS 1, cf. Annexe D §1).
    blank_id: int = 0
    #: Exposant de la normalisation par longueur (``p`` ; optimum mesuré 1.0).
    length_exponent: float = 1.0
    #: Trames minimales par token restant (contrainte de durée, A.5).
    #: 1.0 = simple faisabilité CTC ; augmenter pénalise les candidats longs.
    min_frames_per_token: float = 1.0
    #: Re-score exact (forward CTC complet) des hypothèses finales : neutralise
    #: la masse perdue par l'élagage et reproduit le scoring validé.
    exact_rescore: bool = True
    #: Seuil de rejet sur ``Hypothesis.confidence`` (task 3). ``0.0`` = jamais
    #: rejeter (le décodeur ne fait qu'exposer le signal) ; une valeur > 0 fait
    #: **abstenir** le décodeur quand l'audio ne ressemble pas à un nombre.
    #: Se calibre hors du split de test (``scripts/bench/calibrate_rejection.py``).
    reject_threshold: float = 0.0


@dataclass(frozen=True)
class Hypothesis:
    """Une hypothèse du faisceau : forme canonique valide + scores."""

    #: Forme canonique (mots de la grammaire) — parseable par construction.
    text: str
    #: Séquence d'ids tokenizer retenue (orthographe gagnante).
    token_ids: tuple[int, ...]
    #: ``-log P(token_ids | logits)`` (forward CTC ; plus bas = plus probable).
    neg_log_likelihood: float
    #: NLL normalisée par ``len(token_ids) ** p`` — le score de décision.
    score: float
    #: Confiance de décodage dans ``[0, 1]`` : rapport de vraisemblance par
    #: token émis entre ce chemin contraint et le **meilleur chemin libre** (non
    #: contraint) des mêmes logits — ``exp(-(nll - nll_libre) / nb_tokens)``.
    #: 1.0 = le chemin contraint est aussi probable que le meilleur chemin
    #: possible ; proche de 0 = l'audio ne ressemble pas à un nombre.
    confidence: float


@dataclass(frozen=True)
class DecodeResult:
    """Sortie du décodeur : N meilleures hypothèses, signal de rejet, latence."""

    hypotheses: tuple[Hypothesis, ...]
    frame_count: int
    latency_ms: int
    #: ``-log P`` du meilleur chemin **libre** (référence de comparaison).
    free_path_nll: float = 0.0
    #: Seuil de rejet effectif au moment du décodage (traçabilité).
    reject_threshold: float = 0.0

    @property
    def best(self) -> Hypothesis | None:
        return self.hypotheses[0] if self.hypotheses else None

    @property
    def confidence(self) -> float:
        """Confiance de décodage de la meilleure hypothèse (0.0 si aucune)."""
        best = self.best
        return best.confidence if best is not None else 0.0

    @property
    def rejected(self) -> bool:
        """L'audio doit-il être refusé faute de ressembler à un nombre ?

        Le décodeur **s'abstient** (comme un ASR en échec) plutôt que de
        proposer un nombre : le pipeline en déduit ``number is None`` donc
        ``repeat`` (FR21). Aucune décision parallèle n'est prise ici.
        """
        return self.best is None or self.confidence < self.reject_threshold


# ---------------------------------------------------------------------------
# Briques mathématiques (numpy, log-domaine)
# ---------------------------------------------------------------------------


_LOG2 = math.log(2.0)


def _logaddexp(x: float, y: float) -> float:
    """``np.logaddexp`` sur deux scalaires, **sans le coût de dispatch numpy**.

    Mesuré sur ce VPS : 976 ns pour ``np.logaddexp`` sur des scalaires Python
    contre 204 ns ici — un facteur 4,8. L'opération est appelée des millions de
    fois par décodage (une fois par faisceau et par arc, à chaque trame), donc
    ce facteur se retrouve tel quel dans la latence.

    La séquence de branches reproduit exactement celle de ``npy_logaddexp`` et
    s'appuie sur les mêmes fonctions libm (``exp``, ``log1p``) : la sortie est
    **identique bit à bit**, vérifié sur 60 000 paires couvrant les infinis et
    les extrêmes de l'exposant. Ce n'est donc pas une approximation, et aucune
    hypothèse de décodage ne peut basculer à cause de ce remplacement.
    """
    if x == y:
        return x + _LOG2
    difference = x - y
    if difference > 0:
        return x + math.log1p(math.exp(-difference))
    if difference <= 0:
        return y + math.log1p(math.exp(difference))
    return difference  # NaN se propage, comme dans numpy


def log_softmax(logits: np.ndarray) -> np.ndarray:
    """Log-softmax ligne à ligne, stable ; idempotent sur des log-probs."""
    x = np.asarray(logits, dtype=np.float64)
    x = x - x.max(axis=-1, keepdims=True)
    return x - np.log(np.exp(x).sum(axis=-1, keepdims=True))


def ctc_forward_score(log_probs: np.ndarray, ids: Sequence[int], blank_id: int = 0) -> float:
    """``-log P(ids | log_probs)`` par l'algorithme forward CTC exact.

    Équivalent numpy de ``torch.nn.functional.ctc_loss(reduction="sum")`` sur
    un seul exemple — la fonction de score validée par le prototype, sans
    dépendance torch. ``inf`` si l'alignement est impossible (séquence plus
    longue que le nombre de trames, répétitions comprises).

    La récurrence est **vectorisée sur l'axe des étiquettes étendues**. La
    version précédente parcourait ce même axe en Python : pour un énoncé long
    (375 trames, ~100 étiquettes étendues) cela faisait 37 000 itérations et
    plus de 100 000 ``np.logaddexp`` scalaires par hypothèse — et le rescoring
    s'applique à chaque hypothèse acceptante du faisceau. C'était, de loin, le
    premier poste du décodage (1 424 ms sur ``long_2``).

    Le résultat est **inchangé bit à bit** : mêmes opérations, mêmes ordres
    d'association ; seul l'axe de parcours passe de Python à numpy.
    """
    lp = np.asarray(log_probs, dtype=np.float64)
    frames = lp.shape[0]
    labels = [int(i) for i in ids]

    if not labels:
        # Seule l'alignement tout-blank produit la séquence vide.
        return float(-lp[:, blank_id].sum()) if frames else 0.0

    # Étiquettes étendues : blank entre chaque label et aux extrémités.
    extended = [blank_id]
    for label in labels:
        extended.extend((label, blank_id))
    size = len(extended)

    # Colonnes de `lp` dans l'ordre des étiquettes étendues, rassemblées une
    # seule fois : la boucle sur les trames n'accède plus qu'à des lignes
    # contiguës de taille `size`, au lieu d'indexer la matrice complète.
    emissions = lp[:, extended]

    # Masque du saut de blank : constant sur toute la séquence, donc calculé
    # une fois. Interdit entre deux labels identiques (règle CTC).
    skip = np.zeros(size, dtype=bool)
    for s in range(2, size):
        skip[s] = extended[s] != blank_id and extended[s] != extended[s - 2]

    alpha = np.full(size, -np.inf)
    alpha[0] = lp[0, blank_id]
    if size > 1:
        alpha[1] = lp[0, extended[1]]

    shifted_one = np.empty(size)
    shifted_two = np.empty(size)
    for t in range(1, frames):
        prev = alpha
        shifted_one[0] = -np.inf
        shifted_one[1:] = prev[:-1]
        if size > 2:
            shifted_two[:2] = -np.inf
            np.copyto(shifted_two[2:], prev[:-2], where=skip[2:])
            shifted_two[2:][~skip[2:]] = -np.inf
        else:
            shifted_two[:] = -np.inf
        alpha = np.logaddexp(np.logaddexp(prev, shifted_one), shifted_two) + emissions[t]

    total = alpha[-1] if size == 1 else np.logaddexp(alpha[-1], alpha[-2])
    return float(-total)


def free_path_nll(log_probs: np.ndarray) -> float:
    """``-log P`` du **meilleur chemin libre** (aucune contrainte de grammaire).

    C'est la borne inférieure des NLL atteignables sur ces logits : le décodage
    glouton trame par trame (``argmax``) est optimal quand aucune contrainte ne
    pèse sur la séquence. Sert de **référence** au signal de rejet — comparer le
    chemin contraint à cette borne mesure ce que la contrainte a « coûté »,
    c'est-à-dire à quel point l'audio s'écarte d'un nombre.
    """
    lp = np.asarray(log_probs, dtype=np.float64)
    if lp.shape[0] == 0:
        return 0.0
    return float(-lp.max(axis=-1).sum())


def decoding_confidence(neg_log_likelihood: float, free_nll: float, token_count: int) -> float:
    """Rapport de vraisemblance **par token émis** entre chemin contraint et libre.

    ``exp(-(nll - nll_libre) / nb_tokens)`` ∈ ``[0, 1]`` : coût acoustique moyen,
    par symbole émis, payé pour rester dans la grammaire. 1.0 = la contrainte n'a
    rien coûté (l'audio *est* un nombre) ; proche de 0 = il a fallu forcer.

    **Pourquoi par token et non par trame** (mesuré) : normaliser par la durée
    dilue le coût d'une courte insertion dans un long silence — un silence de
    40 trames « accepte » ``afo`` à 0,59 de confiance, ce qui est faux. Par
    token, le même cas tombe à 0,001 tandis que les nombres nets restent à 1,00.
    C'est en outre la **même** normalisation par la longueur que le scoring
    validé (Annexe A §3, ``p = 1``).

    Ce n'est **pas** un second mécanisme de décision : c'est le signal acoustique
    qui alimente la confiance composite existante (``AsrResult.acoustic_score``),
    laquelle converge vers la politique ``accept | confirm | repeat`` en place.
    """
    if token_count <= 0 or not math.isfinite(neg_log_likelihood):
        return 0.0
    gap = neg_log_likelihood - free_nll
    if gap <= 0.0:  # borne : le chemin contraint ne peut pas battre le libre
        return 1.0
    return float(math.exp(-gap / token_count))


# ---------------------------------------------------------------------------
# Recherche en faisceau contrainte
# ---------------------------------------------------------------------------

_NEG_INF = -math.inf

#: Trames traitées d'un coup par le log-softmax. À 10 288 colonnes en float64,
#: 16 trames font ~1,3 Mo par tableau temporaire : les trois temporaires de la
#: normalisation tiennent alors dans les 8 Mo de cache L3 du processeur, au lieu
#: de faire des allers-retours en RAM. Le résultat est inchangé — la découpe est
#: horizontale et chaque ligne est normalisée indépendamment.
_LOG_SOFTMAX_BLOCK = 16


def _bump(
    beams: dict[tuple[int, tuple[int, ...]], list],
    key: tuple[int, tuple[int, ...]],
    slot: int,
    value: float,
    words: tuple[str, ...],
    last_col: int,
) -> None:
    """Accumule ``value`` (log-domaine) dans ``beams[key][slot]``.

    ``last_col`` est la colonne compacte du dernier id du préfixe, mémorisée avec
    le faisceau : la règle CTC de répétition la relit à chaque trame, et la
    recalculer coûterait une recherche de dictionnaire par faisceau et par trame.
    """
    if value == _NEG_INF:
        return
    entry = beams.get(key)
    if entry is None:
        beams[key] = entry = [_NEG_INF, _NEG_INF, words, last_col]
    entry[slot] = _logaddexp(entry[slot], value)


class ConstrainedCtcDecoder:
    """Prefix beam search CTC restreint à l'automate de la grammaire.

    Chaque faisceau est un **préfixe d'ids distinct** (pas de fusion
    approximative de préfixes différents) portant ses probabilités CTC
    ``(p_blank, p_non_blank)`` et sa position dans l'automate : la mise à jour
    par trame est celle du prefix beam search standard, l'extension n'étant
    autorisée que le long des arcs. Toute hypothèse finale se termine sur un
    état acceptant — la sortie est valide **par construction** (AC1), et la
    sélection est purement acoustique (NFR14).
    """

    def __init__(
        self,
        grammar: NumberGrammar,
        lexicon: TokenLexicon,
        config: DecoderConfig | None = None,
    ) -> None:
        self._config = config if config is not None else DecoderConfig()
        self._automaton = _compile_automaton(grammar, lexicon)
        self._automaton.finalize(
            blank_id=self._config.blank_id,
            min_frames_per_token=self._config.min_frames_per_token,
        )

    @property
    def config(self) -> DecoderConfig:
        return self._config

    def _restricted_log_probs(self, logits: np.ndarray) -> tuple[np.ndarray, float]:
        """Log-probs **restreintes au sous-vocabulaire de la grammaire**, et NLL libre.

        Le log-softmax doit se normaliser sur les 10 288 colonnes — c'est la
        définition. Mais rien n'oblige à *matérialiser* le résultat sur 10 288
        colonnes alors que le décodage n'en lit que 22 : pour un énoncé de 8 s
        cela réduit la matrice transmise à la suite du calcul de 33 Mo à 70 Ko.

        La NLL du chemin libre se déduit du même calcul sans passer par la
        matrice complète : après soustraction du maximum de ligne, ce maximum
        vaut exactement zéro, donc ``max_v log p[t, v] = -denominateur[t]``.

        Les valeurs produites sont **identiques bit à bit** à
        ``log_softmax(logits)[:, used]`` et à ``free_path_nll(log_softmax(logits))`` :
        mêmes opérations dans le même ordre, seules les colonnes inutiles ne sont
        jamais écrites.
        """
        source = np.asarray(logits)
        if source.ndim != 2:
            raise ValueError(f"logits de forme (T, V) attendus, reçu {source.shape}.")
        used = self._automaton.used_ids
        frames = source.shape[0]
        if frames == 0:
            return np.empty((0, len(used)), dtype=np.float64), 0.0

        restricted = np.empty((frames, len(used)), dtype=np.float64)
        denominator = np.empty(frames, dtype=np.float64)

        # Traitement par blocs de trames. Le calcul reste rigoureusement le même
        # — toutes les opérations sont indépendantes ligne à ligne, et la somme
        # par ligne conserve son ordre —, mais les tableaux temporaires cessent
        # d'être proportionnels à la durée de l'audio.
        #
        # En une passe, la version précédente allouait trois matrices
        # ``(T, 10 288)`` en float64 : 99 Mo de trafic mémoire pour 8 s d'audio,
        # bien au-delà des 8 Mo de cache L3 de ce processeur. Par blocs, les
        # temporaires tiennent dans le cache et la mémoire de pointe du décodage
        # devient indépendante de la longueur de l'énoncé.
        for start in range(0, frames, _LOG_SOFTMAX_BLOCK):
            stop = min(start + _LOG_SOFTMAX_BLOCK, frames)
            block = source[start:stop].astype(np.float64)
            block -= block.max(axis=-1, keepdims=True)
            block_denominator = np.log(np.exp(block).sum(axis=-1))
            denominator[start:stop] = block_denominator
            restricted[start:stop] = block[:, used] - block_denominator[:, None]

        return restricted, float(denominator.sum())

    def decode(self, logits: np.ndarray) -> DecodeResult:
        """Décode des logits ``(T, V)`` (ou log-probs : log_softmax idempotent)."""
        started = time.perf_counter()
        cfg = self._config
        aut = self._automaton
        restricted, free_nll = self._restricted_log_probs(logits)
        frames = restricted.shape[0]
        blank_col = aut.col_of[cfg.blank_id]
        beam_width = cfg.beam_width

        # Lignes converties en listes Python : l'arithmétique du faisceau se fait
        # alors sur des `float` natifs et non des `np.float64`, dont chaque
        # opération repasse par le dispatch numpy. Les valeurs sont les mêmes
        # (double IEEE dans les deux cas) — seul le coût par opération change.
        rows = restricted.tolist()
        fast_arcs = aut.fast_arcs

        # clé = (nœud, préfixe d'ids) ;
        # valeur = [p_blank, p_non_blank, mots, colonne du dernier id].
        beams: dict[tuple[int, tuple[int, ...]], list] = {(aut.start, ()): [0.0, _NEG_INF, (), -1]}

        for t in range(frames):
            frame = rows[t]
            remaining = frames - t - 1
            blank_score = frame[blank_col]
            nxt: dict[tuple[int, tuple[int, ...]], list] = {}

            for (node, ids), (p_b, p_nb, words, last_col) in beams.items():
                total = _logaddexp(p_b, p_nb)
                # 1) blank : le préfixe ne change pas.
                _bump(nxt, (node, ids), 0, total + blank_score, words, last_col)
                # 2) répétition du dernier token : absorbée (pas d'émission).
                if ids:
                    _bump(nxt, (node, ids), 1, p_nb + frame[last_col], words, last_col)
                # 3) extensions le long des arcs de l'automate.
                last_id = ids[-1] if ids else None
                for token_id, col, next_node, emitted, min_frames in fast_arcs[node]:
                    # Contrainte de durée / faisabilité : chaque token restant
                    # exige min_frames_per_token trames (principe acoustique).
                    if min_frames > remaining:
                        continue
                    # CTC : étendre avec le même token que le dernier émis
                    # nécessite un blank intermédiaire → part de p_b seul.
                    base = p_b if token_id == last_id else total
                    if base == _NEG_INF:
                        continue
                    new_words = words + (emitted,) if emitted else words
                    _bump(
                        nxt,
                        (next_node, ids + (token_id,)),
                        1,
                        base + frame[col],
                        new_words,
                        col,
                    )

            if len(nxt) > beam_width:
                # L'ordre du dictionnaire conservé influe sur l'ordre
                # d'accumulation de la trame suivante, donc sur les derniers bits
                # des scores : on trie systématiquement, comme avant, plutôt que
                # de court-circuiter quand l'élagage ne retire rien.
                beams = dict(
                    sorted(nxt.items(), key=lambda kv: -_logaddexp(kv[1][0], kv[1][1]))[:beam_width]
                )
            else:
                beams = dict(sorted(nxt.items(), key=lambda kv: -_logaddexp(kv[1][0], kv[1][1])))

        # Hypothèses finales : uniquement les préfixes terminés sur un état
        # acceptant. Les orthographes convergentes (mêmes mots canoniques via
        # des ids différents) sont fusionnées en gardant le meilleur score.
        col_of = aut.col_of
        blank_for_rescore = blank_col
        by_text: dict[str, Hypothesis] = {}
        for (node, ids), (p_b, p_nb, words, _last_col) in beams.items():
            if node not in aut.accepting or not ids:
                continue
            nll = float(-_logaddexp(p_b, p_nb))
            if cfg.exact_rescore:
                # Rescoring sur la matrice restreinte : mêmes valeurs, donc même
                # score, en parcourant 22 colonnes au lieu de 10 288.
                nll = ctc_forward_score(restricted, [col_of[i] for i in ids], blank_for_rescore)
            score = nll / (len(ids) ** cfg.length_exponent)
            text = " ".join(words)
            current = by_text.get(text)
            if current is None or score < current.score:
                by_text[text] = Hypothesis(
                    text=text,
                    token_ids=ids,
                    neg_log_likelihood=nll,
                    score=score,
                    confidence=decoding_confidence(nll, free_nll, len(ids)),
                )

        hypotheses = tuple(sorted(by_text.values(), key=lambda h: (h.score, h.text))[: cfg.nbest])
        latency_ms = int((time.perf_counter() - started) * 1000)
        return DecodeResult(
            hypotheses=hypotheses,
            frame_count=frames,
            latency_ms=latency_ms,
            free_path_nll=free_nll,
            reject_threshold=cfg.reject_threshold,
        )


__all__ = [
    "TokenLexicon",
    "build_token_lexicon",
    "DecoderConfig",
    "Hypothesis",
    "DecodeResult",
    "ConstrainedCtcDecoder",
    "ctc_forward_score",
    "decoding_confidence",
    "free_path_nll",
    "log_softmax",
]
