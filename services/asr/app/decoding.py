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

    def new_node(self) -> int:
        self.arcs.append([])
        return len(self.arcs) - 1


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

    alpha = np.full(size, -np.inf)
    alpha[0] = lp[0, blank_id]
    if size > 1:
        alpha[1] = lp[0, extended[1]]
    for t in range(1, frames):
        prev = alpha
        alpha = np.full(size, -np.inf)
        for s in range(size):
            best = prev[s]
            if s >= 1:
                best = np.logaddexp(best, prev[s - 1])
            # Saut du blank intermédiaire, interdit entre labels identiques.
            if s >= 2 and extended[s] != blank_id and extended[s] != extended[s - 2]:
                best = np.logaddexp(best, prev[s - 2])
            alpha[s] = best + lp[t, extended[s]]
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


def _bump(
    beams: dict[tuple[int, tuple[int, ...]], list],
    key: tuple[int, tuple[int, ...]],
    slot: int,
    value: float,
    words: tuple[str, ...],
) -> None:
    """Accumule ``value`` (log-domaine) dans ``beams[key][slot]``."""
    if value == _NEG_INF:
        return
    entry = beams.get(key)
    if entry is None:
        beams[key] = entry = [_NEG_INF, _NEG_INF, words]
    entry[slot] = np.logaddexp(entry[slot], value)


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

    @property
    def config(self) -> DecoderConfig:
        return self._config

    def decode(self, logits: np.ndarray) -> DecodeResult:
        """Décode des logits ``(T, V)`` (ou log-probs : log_softmax idempotent)."""
        started = time.perf_counter()
        lp = log_softmax(logits)
        if lp.ndim != 2:
            raise ValueError(f"logits de forme (T, V) attendus, reçu {lp.shape}.")
        frames = lp.shape[0]
        cfg = self._config
        aut = self._automaton
        blank = cfg.blank_id

        # clé = (nœud, préfixe d'ids) ; valeur = [p_blank, p_non_blank, mots].
        beams: dict[tuple[int, tuple[int, ...]], list] = {(aut.start, ()): [0.0, _NEG_INF, ()]}

        for t in range(frames):
            frame = lp[t]
            remaining = frames - t - 1
            nxt: dict[tuple[int, tuple[int, ...]], list] = {}

            for (node, ids), (p_b, p_nb, words) in beams.items():
                total = np.logaddexp(p_b, p_nb)
                # 1) blank : le préfixe ne change pas.
                _bump(nxt, (node, ids), 0, total + frame[blank], words)
                # 2) répétition du dernier token : absorbée (pas d'émission).
                if ids:
                    _bump(nxt, (node, ids), 1, p_nb + frame[ids[-1]], words)
                # 3) extensions le long des arcs de l'automate.
                for token_id, next_node, emitted in aut.arcs[node]:
                    # Contrainte de durée / faisabilité : chaque token restant
                    # exige min_frames_per_token trames (principe acoustique).
                    if aut.min_tokens[next_node] * cfg.min_frames_per_token > remaining:
                        continue
                    # CTC : étendre avec le même token que le dernier émis
                    # nécessite un blank intermédiaire → part de p_b seul.
                    base = p_b if (ids and token_id == ids[-1]) else total
                    if base == _NEG_INF:
                        continue
                    new_words = words + (emitted,) if emitted else words
                    _bump(nxt, (next_node, ids + (token_id,)), 1, base + frame[token_id], new_words)

            pruned = sorted(nxt.items(), key=lambda kv: -np.logaddexp(kv[1][0], kv[1][1]))[
                : cfg.beam_width
            ]
            beams = dict(pruned)

        # Hypothèses finales : uniquement les préfixes terminés sur un état
        # acceptant. Les orthographes convergentes (mêmes mots canoniques via
        # des ids différents) sont fusionnées en gardant le meilleur score.
        free_nll = free_path_nll(lp)
        by_text: dict[str, Hypothesis] = {}
        for (node, ids), (p_b, p_nb, words) in beams.items():
            if node not in aut.accepting or not ids:
                continue
            nll = float(-np.logaddexp(p_b, p_nb))
            if cfg.exact_rescore:
                nll = ctc_forward_score(lp, ids, blank)
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
