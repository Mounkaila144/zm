"""Tests du décodeur CTC contraint (story 5.6, task 2) — sans GPU, sans modèle.

Un tokenizer jouet (caractère → id, spéciaux 0..3 réservés comme le vrai
tokenizer Omnilingual) et des logits synthétiques suffisent : le décodeur est
agnostique du modèle. Les propriétés prouvées ici :

- toute sortie appartient à la grammaire et est parseable (AC1) ;
- la recherche couvre l'espace sans énumération, via l'automate (AC2) ;
- le scoring est le forward CTC exact normalisé par la longueur (Annexe A §3) ;
- la contrainte de durée élague les candidats trop longs pour l'audio (A.5) ;
- les N meilleures hypothèses sont exposées avec leurs scores (marge) ;
- la latence est mesurée et reste dans un budget CPU raisonnable (NFR1).
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import pytest
from zarma_numbers.generator import generate
from zarma_numbers.grammar import load_grammar
from zarma_numbers.parser import parse

# --- Tokenizer jouet : caractère -> id, ids spéciaux 0..3 réservés ---

_ALPHABET = "abcdefghijklmnopqrstuvwxyz "
_CHAR_TO_ID = {char: 4 + i for i, char in enumerate(_ALPHABET)}
_VOCAB_SIZE = 4 + len(_ALPHABET) + 3  # marge : ids jamais émis par le lexique
_BLANK = 0
_SPACE_ID = _CHAR_TO_ID[" "]


def _toy_encode(text: str) -> list[int]:
    return [_CHAR_TO_ID[char] for char in text]


def _synthetic_logits(
    text: str,
    *,
    frames_per_token: int = 2,
    strength: float = 8.0,
    noise: float = 0.0,
    seed: int = 0,
) -> np.ndarray:
    """Logits (T, V) favorisant fortement la chaîne ``text`` alignée en CTC.

    Un blank est inséré entre les tokens (nécessaire entre caractères répétés,
    inoffensif ailleurs) — exactement la structure qu'un modèle CTC produit.
    """
    ids = _toy_encode(text)
    frame_ids: list[int] = []
    for token_id in ids:
        frame_ids.extend([token_id] * frames_per_token)
        frame_ids.append(_BLANK)
    rng = np.random.default_rng(seed)
    logits = rng.normal(0.0, noise, size=(len(frame_ids), _VOCAB_SIZE))
    for t, token_id in enumerate(frame_ids):
        logits[t, token_id] += strength
    return logits


@pytest.fixture(scope="module")
def grammar():
    return load_grammar()


@pytest.fixture(scope="module")
def lexicon(decoding, grammar):
    return decoding.build_token_lexicon(
        grammar, _toy_encode, separator=(_SPACE_ID,), blank_id=_BLANK
    )


@pytest.fixture(scope="module")
def decoder(decoding, grammar, lexicon):
    return decoding.ConstrainedCtcDecoder(grammar, lexicon)


# --- AC1/AC2 : décodage correct des formes générées, sans énumération ---


@pytest.mark.parametrize("n", [0, 1, 9, 11, 42, 100, 101, 372, 1000, 1234, 100005, 1000000])
def test_decodes_clean_synthetic_utterances(decoder, n):
    text = generate(n)
    result = decoder.decode(_synthetic_logits(text))
    assert result.best is not None
    assert result.best.text == text
    assert parse(result.best.text) == n


def test_search_space_is_the_automaton_not_an_enumeration(decoding, grammar, lexicon):
    # 1 234 567 formes énumérées seraient intraitables ; l'automate compilé
    # reste compact et le décodage d'un énoncé long tient en quelques centaines
    # de millisecondes (cf. test de latence) : la couverture 0–1 000 000 vient
    # de la structure, pas d'une liste de candidats.
    automaton = decoding._compile_automaton(grammar, lexicon)
    assert len(automaton.arcs) < 200_000
    assert automaton.accepting


def test_noise_only_output_is_still_grammatical(decoder, grammar):
    # Sans mécanisme de rejet (task 3), le décodeur peut retourner une
    # hypothèse sur du bruit — mais **jamais** une chaîne hors grammaire.
    rng = np.random.default_rng(20260725)
    logits = rng.normal(0.0, 3.0, size=(30, _VOCAB_SIZE))
    result = decoder.decode(logits)
    for hypothesis in result.hypotheses:
        assert grammar.accepts(hypothesis.text)
        assert parse(hypothesis.text) is not None


def test_invalid_form_audio_never_yields_invalid_text(decoder, grammar):
    # Audio « waranka cindi afo » (forme interdite : unité isolée en position
    # combinée) : quelle que soit l'hypothèse retenue, elle reste valide.
    result = decoder.decode(_synthetic_logits("waranka cindi afo"))
    for hypothesis in result.hypotheses:
        assert grammar.accepts(hypothesis.text)


def test_empty_audio_yields_no_hypothesis(decoder):
    result = decoder.decode(np.zeros((0, _VOCAB_SIZE)))
    assert result.hypotheses == ()
    assert result.best is None
    assert result.frame_count == 0


# --- Prononciations alternatives : convergence vers la forme canonique ---


def test_variant_pronunciation_converges_to_canonical(decoder):
    # « nda » est une variante linguistique de « da » (lexique v1.2.0) : l'audio
    # « zangou nda fo » doit produire la forme canonique « zangou da fo ».
    result = decoder.decode(_synthetic_logits("zangou nda fo"))
    assert result.best is not None
    assert result.best.text == "zangou da fo"
    assert parse(result.best.text) == 101


def test_connector_distribution_constrains_decoding(decoder, grammar):
    # Distribution complémentaire da/di (lexique v1.2.0) : un audio « zangou da
    # hinka » (connecteur interdit devant 2) ne peut pas produire cette forme —
    # toute hypothèse retenue reste dans la grammaire.
    result = decoder.decode(_synthetic_logits("zangou da hinka"))
    for hypothesis in result.hypotheses:
        assert hypothesis.text != "zangou da hinka"
        assert grammar.accepts(hypothesis.text)
    # La forme correcte, elle, se décode telle quelle (avec élision pour 110).
    assert decoder.decode(_synthetic_logits("zangou di hinka")).best.text == "zangou di hinka"
    assert decoder.decode(_synthetic_logits("zangou di wey")).best.text == "zangou di wey"


def test_asr_confusions_are_not_in_the_decoding_lexicon(lexicon):
    # FR8 : « zangu » est une correction ASR, pas une variante linguistique —
    # aucun encodage du lexique de décodage ne doit y correspondre.
    zangu_ids = tuple(_toy_encode("zangu"))
    for encodings in lexicon.entries.values():
        assert zangu_ids not in encodings


# --- Scoring : forward CTC exact, normalisation par la longueur ---


def _brute_force_nll(log_probs: np.ndarray, labels: list[int], blank: int) -> float:
    """Somme exhaustive sur tous les alignements (petites dimensions)."""
    frames, vocab = log_probs.shape
    total = -math.inf
    for path in itertools.product(range(vocab), repeat=frames):
        collapsed = [k for k, _ in itertools.groupby(path) if k != blank]
        if collapsed == labels:
            total = np.logaddexp(total, sum(log_probs[t, k] for t, k in enumerate(path)))
    return float(-total)


@pytest.mark.parametrize("labels", [[4], [4, 5], [4, 4], [5, 4, 5]])
def test_ctc_forward_matches_brute_force(decoding, labels):
    rng = np.random.default_rng(42)
    log_probs = decoding.log_softmax(rng.normal(size=(4, 6)))
    expected = _brute_force_nll(log_probs, labels, blank=_BLANK)
    got = decoding.ctc_forward_score(log_probs, labels, blank_id=_BLANK)
    assert got == pytest.approx(expected, rel=1e-9)


def test_ctc_forward_infeasible_alignment_is_infinite(decoding):
    log_probs = decoding.log_softmax(np.zeros((2, 6)))
    # 3 labels en 2 trames : impossible.
    assert decoding.ctc_forward_score(log_probs, [4, 5, 4], blank_id=_BLANK) == math.inf
    # 2 labels identiques en 2 trames : blank intermédiaire requis → impossible.
    assert decoding.ctc_forward_score(log_probs, [4, 4], blank_id=_BLANK) == math.inf


def test_beam_probability_matches_exact_forward(decoding, grammar, lexicon):
    # Sans re-score exact et avec un faisceau large, la probabilité accumulée
    # par le prefix beam search doit retrouver le forward exact du gagnant.
    config = decoding.DecoderConfig(beam_width=512, exact_rescore=False)
    wide = decoding.ConstrainedCtcDecoder(grammar, lexicon, config)
    logits = _synthetic_logits("waranka cindi fo", noise=0.5, seed=7)
    best = wide.decode(logits).best
    assert best is not None
    exact = decoding.ctc_forward_score(decoding.log_softmax(logits), best.token_ids, _BLANK)
    assert best.neg_log_likelihood == pytest.approx(exact, rel=1e-6)


def test_scores_are_length_normalized(decoding, grammar, lexicon, decoder):
    # p = 0 (score brut) contre p = 1 (validé) : la normalisation change le
    # score exactement d'un facteur len(ids) — jamais la validité des formes.
    raw_config = decoding.DecoderConfig(length_exponent=0.0)
    raw_decoder = decoding.ConstrainedCtcDecoder(grammar, lexicon, raw_config)
    logits = _synthetic_logits("iwey cindi fo")
    normalized = decoder.decode(logits).best
    raw = raw_decoder.decode(logits).best
    assert normalized is not None and raw is not None
    assert raw.score == pytest.approx(raw.neg_log_likelihood)
    assert normalized.score == pytest.approx(
        normalized.neg_log_likelihood / len(normalized.token_ids)
    )


# --- N meilleures hypothèses (signal de marge pour la confiance composite) ---


def test_nbest_is_sorted_with_finite_scores(decoder):
    result = decoder.decode(_synthetic_logits("waranka cindi hinza", noise=1.0, seed=3))
    assert 1 <= len(result.hypotheses) <= decoder.config.nbest
    scores = [hypothesis.score for hypothesis in result.hypotheses]
    assert scores == sorted(scores)
    assert all(math.isfinite(score) for score in scores)
    texts = [hypothesis.text for hypothesis in result.hypotheses]
    assert len(texts) == len(set(texts))  # pas de doublon de forme canonique


def test_nbest_size_is_configurable(decoding, grammar, lexicon):
    config = decoding.DecoderConfig(nbest=2)
    small = decoding.ConstrainedCtcDecoder(grammar, lexicon, config)
    result = small.decode(_synthetic_logits("afo", noise=1.0, seed=5))
    assert len(result.hypotheses) <= 2


# --- Contrainte de durée (mode d'échec A.5 : court apparié à long) ---


def test_hypotheses_respect_ctc_feasibility(decoder):
    # 6 trames uniformes : aucune hypothèse ne peut porter plus de 6 tokens.
    logits = np.zeros((6, _VOCAB_SIZE))
    result = decoder.decode(logits)
    for hypothesis in result.hypotheses:
        assert len(hypothesis.token_ids) <= 6


def test_min_frames_per_token_prunes_long_candidates(decoding, grammar, lexicon):
    # Avec 3 trames minimum par token, 12 trames ne peuvent porter que des
    # formes de 4 tokens au plus (« afo » tient, « waranka cindi fo » non).
    config = decoding.DecoderConfig(min_frames_per_token=3.0)
    strict = decoding.ConstrainedCtcDecoder(grammar, lexicon, config)
    logits = np.zeros((12, _VOCAB_SIZE))
    result = strict.decode(logits)
    assert result.hypotheses  # les formes courtes restent atteignables
    for hypothesis in result.hypotheses:
        assert len(hypothesis.token_ids) <= 4


def test_short_utterance_prefers_short_candidate(decoder):
    # Scénario A.5 en miniature : un énoncé court et net (« afo ») ne doit pas
    # être apparié à un candidat long.
    result = decoder.decode(_synthetic_logits("afo"))
    assert result.best is not None
    assert result.best.text == "afo"


# --- Latence (NFR1 : mesurée et exposée) ---


def test_latency_is_measured_and_within_cpu_budget(decoder):
    # Dimensions réalistes : T=50 trames (~1 s d'audio), V=10 288 (Annexe A §2).
    rng = np.random.default_rng(1)
    logits = rng.normal(0.0, 2.0, size=(50, 10_288))
    result = decoder.decode(logits)
    assert result.frame_count == 50
    assert result.latency_ms >= 0
    # Budget CPU volontairement large pour une CI partagée ; la valeur typique
    # mesurée (M1, CPU) est consignée dans le Dev Agent Record de la story.
    assert result.latency_ms < 5_000


def test_decode_rejects_bad_shapes(decoder):
    with pytest.raises(ValueError):
        decoder.decode(np.zeros(10))


# --- Lexique de décodage : validations ---


def test_lexicon_rejects_blank_in_encoding(decoding, grammar):
    def bad_encode(text: str) -> list[int]:
        return [_BLANK] + _toy_encode(text)

    with pytest.raises(ValueError):
        decoding.build_token_lexicon(grammar, bad_encode, blank_id=_BLANK)


def test_lexicon_rejects_empty_encoding(decoding, grammar):
    with pytest.raises(ValueError):
        decoding.build_token_lexicon(grammar, lambda text: [], blank_id=_BLANK)


def test_lexicon_covers_every_grammar_token_with_pronunciations(lexicon, grammar):
    assert set(lexicon.entries) == set(grammar.tokens)
    # « da » possède sa variante « nda » → au moins 2 encodages ; « di » et
    # « wey » (forme élidée) sont des tokens à part entière.
    assert len(lexicon.entries["da"]) >= 2
    assert lexicon.entries["di"]
    assert lexicon.entries["wey"]
