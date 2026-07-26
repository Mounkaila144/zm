"""Non-régression des optimisations de performance (décodage et pré-traitement).

Les changements couverts ici ont été faits pour la vitesse, jamais pour la
qualité. La façon la plus solide de le garantir n'est pas de rejouer quinze
enregistrements figés : c'est de prouver, **sur des entrées aléatoires**, que
chaque chemin rapide donne exactement ce que donnait le chemin lent. Une fixture
enregistrée ne teste que le cas enregistré ; une propriété tient sur tout le
domaine.

D'où le parti pris : les fonctions optimisées sont confrontées à une
implémentation **naïve écrite dans le test**, et l'égalité exigée est l'égalité
**bit à bit** — pas une tolérance. Une différence d'un ulp sur une NLL peut
inverser deux hypothèses proches et changer la décision ``accept`` / ``confirm``
rendue à l'usager ; tant que l'exactitude est atteignable, la relâcher reviendrait
à ne plus pouvoir affirmer que la reconnaissance est inchangée.

La VAD, elle, n'est pas exacte par nature — elle retire des trames. Ses tests
portent donc sur ce qui ne doit jamais arriver : déclarer muette une parole
faible, ou rogner à l'intérieur d'un énoncé.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"
EXPRESSION_LEXICON = FIXTURES / "expression-token-lexicon.json"


# ---------------------------------------------------------------------------
# logaddexp scalaire
# ---------------------------------------------------------------------------


def test_scalar_logaddexp_matches_numpy_bit_for_bit(decoding):
    """Le remplacement de ``np.logaddexp`` ne doit rien changer, jamais.

    Couvre explicitement les ``-inf`` (faisceaux morts, chemins interdits) et le
    voisinage du seuil de sous-écoulement de ``exp`` : ce sont exactement les
    régions où une implémentation naïve de ``log(exp(x) + exp(y))`` divergerait.
    """
    rng = np.random.default_rng(20240726)
    values = list(rng.uniform(-800.0, 20.0, 4000))
    values += [-math.inf, 0.0, -745.0, -746.0, -1e-300, 1e-300, 700.0]
    for index, x in enumerate(values):
        y = values[(index * 7919 + 13) % len(values)]
        expected = float(np.logaddexp(x, y))
        actual = decoding._logaddexp(x, y)
        assert actual == expected or (
            math.isnan(actual) and math.isnan(expected)
        ), f"logaddexp({x}, {y}) : {actual!r} != {expected!r}"


# ---------------------------------------------------------------------------
# forward CTC vectorisé
# ---------------------------------------------------------------------------


def _naive_ctc_forward(log_probs: np.ndarray, ids: list[int], blank: int) -> float:
    """Récurrence forward CTC, écrite ligne à ligne (version d'origine)."""
    lp = np.asarray(log_probs, dtype=np.float64)
    frames = lp.shape[0]
    if not ids:
        return float(-lp[:, blank].sum()) if frames else 0.0
    extended = [blank]
    for label in ids:
        extended.extend((label, blank))
    size = len(extended)
    alpha = np.full(size, -np.inf)
    alpha[0] = lp[0, blank]
    if size > 1:
        alpha[1] = lp[0, extended[1]]
    for t in range(1, frames):
        prev = alpha
        alpha = np.full(size, -np.inf)
        for s in range(size):
            best = prev[s]
            if s >= 1:
                best = np.logaddexp(best, prev[s - 1])
            if s >= 2 and extended[s] != blank and extended[s] != extended[s - 2]:
                best = np.logaddexp(best, prev[s - 2])
            alpha[s] = best + lp[t, extended[s]]
    total = alpha[-1] if size == 1 else np.logaddexp(alpha[-1], alpha[-2])
    return float(-total)


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_vectorised_ctc_forward_matches_naive(decoding, seed):
    """Même score, bit à bit, y compris quand l'alignement est infaisable."""
    rng = np.random.default_rng(seed)
    frames = int(rng.integers(1, 40))
    vocab = 9
    log_probs = decoding.log_softmax(rng.normal(0.0, 3.0, size=(frames, vocab)))
    length = int(rng.integers(1, 12))
    ids = [int(rng.integers(1, vocab)) for _ in range(length)]
    assert decoding.ctc_forward_score(log_probs, ids, 0) == _naive_ctc_forward(log_probs, ids, 0)


def test_vectorised_ctc_forward_handles_repeated_labels(decoding):
    """Deux labels identiques consécutifs interdisent le saut du blank.

    C'est la seule règle de la récurrence qui dépend du contenu de la séquence :
    la vectorisation la porte dans un masque, et une erreur de masque donnerait
    un score trop bas — donc une hypothèse artificiellement favorisée.
    """
    rng = np.random.default_rng(7)
    log_probs = decoding.log_softmax(rng.normal(0.0, 2.0, size=(25, 7)))
    for ids in ([3, 3], [1, 1, 1], [2, 2, 5, 5], [4, 4, 4, 4, 6]):
        assert decoding.ctc_forward_score(log_probs, ids, 0) == _naive_ctc_forward(
            log_probs, ids, 0
        )


def test_vectorised_ctc_forward_reports_infeasible_as_infinite(decoding):
    """Séquence plus longue que l'audio : score infini, pas un score fini faux."""
    log_probs = decoding.log_softmax(np.zeros((3, 6)))
    assert math.isinf(decoding.ctc_forward_score(log_probs, [1, 2, 3, 4, 5], 0))


# ---------------------------------------------------------------------------
# log-probs restreintes au sous-vocabulaire de la grammaire
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def expression_decoder(decoding):
    """Décodeur sur la grammaire des **expressions** et le lexique réel.

    Le lexique est celui du tokenizer Omnilingual, sondé une fois et versionné :
    les tests portent donc sur l'automate réellement servi en production, sans
    exiger le modèle (2 Go) ni le tokenizer.
    """
    from zarma_numbers.grammar import load_expression_grammar

    payload = json.loads(EXPRESSION_LEXICON.read_text(encoding="utf-8"))
    entries = {
        word: tuple(tuple(int(i) for i in ids) for ids in spellings)
        for word, spellings in payload["entries"].items()
    }
    lexicon = decoding.TokenLexicon(
        entries=entries, separator=tuple(int(i) for i in payload["separator"])
    )
    return decoding.ConstrainedCtcDecoder(
        load_expression_grammar(), lexicon, decoding.DecoderConfig(beam_width=32)
    )


def test_restricted_log_probs_match_full_log_softmax(decoding, expression_decoder):
    """La matrice restreinte est exactement la matrice complète, colonnes utiles.

    Et la NLL du chemin libre — qui sert de référence à la confiance, donc au
    seuil de rejet — est identique alors qu'elle n'est plus calculée sur la
    matrice complète.
    """
    rng = np.random.default_rng(11)
    logits = rng.normal(0.0, 4.0, size=(37, 10288)).astype(np.float32)

    restricted, free_nll = expression_decoder._restricted_log_probs(logits)
    full = decoding.log_softmax(logits)
    used = list(expression_decoder._automaton.used_ids)

    assert restricted.shape == (37, len(used))
    assert np.array_equal(restricted, full[:, used])
    assert free_nll == decoding.free_path_nll(full)


def test_restricted_vocabulary_covers_every_reachable_token(expression_decoder):
    """Un id atteignable absent du sous-vocabulaire ferait planter le décodage.

    La restriction n'est sûre que si elle est exhaustive : ce test relit
    l'automate compilé plutôt que de faire confiance à la construction.
    """
    automaton = expression_decoder._automaton
    used = set(automaton.used_ids)
    assert expression_decoder.config.blank_id in used
    for node_arcs in automaton.arcs:
        for token_id, _, _ in node_arcs:
            assert token_id in used
            assert automaton.col_of[token_id] < len(automaton.used_ids)


def test_restricted_log_probs_accept_empty_input(expression_decoder):
    """Zéro trame : pas d'exception, et une NLL libre nulle."""
    restricted, free_nll = expression_decoder._restricted_log_probs(
        np.zeros((0, 10288), dtype=np.float32)
    )
    assert restricted.shape[0] == 0
    assert free_nll == 0.0


# ---------------------------------------------------------------------------
# Sorties du décodeur : grammaticalité, silence, décisions
# ---------------------------------------------------------------------------


def test_noise_only_stays_inside_the_grammar(expression_decoder):
    """Sur du bruit, la sortie reste grammaticale — jamais un texte inventé."""
    from zarma_numbers.grammar import load_expression_grammar

    grammar = load_expression_grammar()
    rng = np.random.default_rng(3)
    result = expression_decoder.decode(rng.normal(0.0, 1.0, size=(60, 10288)).astype(np.float32))
    for hypothesis in result.hypotheses:
        state = grammar.start
        for word in hypothesis.text.split():
            transitions = grammar.transitions(state)
            assert word in transitions, f"« {hypothesis.text} » sort de la grammaire"
            state = transitions[word]
        assert grammar.is_accepting(state)


def test_zero_frames_yields_abstention(expression_decoder):
    """Aucune trame : aucune hypothèse, donc abstention — jamais un nombre."""
    result = expression_decoder.decode(np.zeros((0, 10288), dtype=np.float32))
    assert result.hypotheses == ()
    assert result.best is None
    assert result.confidence == 0.0


def test_confidence_stays_within_unit_interval(expression_decoder):
    """La confiance alimente les seuils accept/confirm : elle doit rester bornée."""
    rng = np.random.default_rng(5)
    for _ in range(4):
        logits = rng.normal(0.0, 3.0, size=(50, 10288)).astype(np.float32)
        result = expression_decoder.decode(logits)
        for hypothesis in result.hypotheses:
            assert 0.0 <= hypothesis.confidence <= 1.0
            assert math.isfinite(hypothesis.score)


def test_decode_memory_stays_proportional_to_used_vocabulary(expression_decoder):
    """Le décodage ne doit plus matérialiser de matrice ``(T, 10288)`` en float64.

    C'est ce qui rendait le décodeur coûteux en mémoire autant qu'en temps : sur
    8 secondes d'audio, trois temporaires de 33 Mo transitaient par la RAM à
    chaque requête. Le budget vérifié ici est volontairement large — il échoue
    si la restriction au sous-vocabulaire disparaît, pas au moindre écart.
    """
    import tracemalloc

    logits = np.random.default_rng(9).normal(0.0, 2.0, size=(400, 10288)).astype(np.float32)
    tracemalloc.start()
    before = tracemalloc.get_traced_memory()[0]
    expression_decoder.decode(logits)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    # (400, 10288) en float64 = 33 Mo ; on exige de rester sous deux de ces
    # matrices, ce que la version restreinte fait très largement.
    assert peak - before < 70 * 1024 * 1024


# ---------------------------------------------------------------------------
# Élagage des silences
# ---------------------------------------------------------------------------


def _tone(seconds: float, amplitude: float = 0.3, rate: int = 16_000, seed: int = 0) -> np.ndarray:
    """Signal de parole synthétique : bruit modulé, spectre large."""
    rng = np.random.default_rng(seed)
    samples = rng.normal(0.0, amplitude, size=int(seconds * rate)).astype(np.float32)
    envelope = 0.5 + 0.5 * np.sin(np.linspace(0.0, 20.0, samples.size))
    return (samples * envelope).astype(np.float32)


def test_digital_silence_is_detected(vad):
    """Silence numérique : détecté, donc le modèle n'est jamais appelé."""
    result = vad.analyse(np.zeros(16_000 * 8, dtype=np.float32), 16_000)
    assert result.is_silent is True


def test_weak_speech_is_never_declared_silent(vad):
    """Une prise faible (micro éloigné) reste de la parole.

    C'est l'erreur à ne pas commettre : la déclarer muette transformerait un
    énoncé valide en abstention, donc en ``repeat`` — une régression de qualité
    invisible dans les mesures de latence.
    """
    for amplitude in (0.05, 0.02, 0.01, 0.005):
        signal = _tone(4.0, amplitude=amplitude)
        assert vad.analyse(signal, 16_000).is_silent is False, f"amplitude {amplitude}"


def test_edge_silence_is_trimmed_but_speech_is_preserved(vad):
    """Les bords muets partent ; l'intégralité de la parole reste.

    On vérifie l'énergie conservée, pas seulement les durées : une coupe qui
    tomberait un peu trop à l'intérieur raccourcirait le premier mot sans
    changer grand-chose au compte de secondes.
    """
    rate = 16_000
    speech = _tone(3.0, amplitude=0.3, seed=1)
    pad = np.zeros(int(1.5 * rate), dtype=np.float32)
    padded = np.concatenate([pad, speech, pad])

    result = vad.analyse(padded, rate)
    assert result.is_silent is False
    assert result.kept_seconds < result.original_seconds
    assert result.kept_seconds >= 3.0  # toute la parole, au moins
    assert float(np.sum(result.samples**2)) == pytest.approx(float(np.sum(speech**2)), rel=1e-6)


def test_interior_pauses_are_never_removed(vad):
    """Une pause entre deux mots fait partie de l'énoncé : elle doit survivre."""
    rate = 16_000
    part = _tone(1.5, amplitude=0.3, seed=2)
    gap = np.zeros(int(1.0 * rate), dtype=np.float32)
    signal = np.concatenate([part, gap, part])
    result = vad.analyse(signal, rate)
    assert result.samples.size == signal.size
    assert result.trimmed_seconds == 0.0


def test_speech_without_edge_silence_is_left_untouched(vad):
    """Rien à gagner, rien à risquer : le signal doit passer tel quel."""
    signal = _tone(5.0, amplitude=0.3, seed=3)
    result = vad.analyse(signal, 16_000)
    assert result.samples.size == signal.size


def test_very_short_input_is_not_truncated(vad):
    """Un énoncé plus court que la marge ne doit pas être réduit à néant."""
    signal = _tone(0.3, amplitude=0.3, seed=4)
    result = vad.analyse(signal, 16_000)
    assert result.samples.size == signal.size
