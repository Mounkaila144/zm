"""Tests de validité du décodeur (story 5.6, task 6) — sans GPU, sans modèle.

Deux garanties, prouvées par propriété plutôt que par cas :

1. **Validité** : toute sortie du décodeur est parseable et re-génère la même
   forme canonique — quel que soit le contenu des logits (même du bruit pur).
2. **Fixtures de logits** : le décodeur se teste sur des tenseurs ``.npz``
   chargés depuis le disque, sans modèle ni GPU, exactement comme le fera la CI
   avec des logits réels dumpés par ``scripts/bench/decode_constrained.py``.
"""

from __future__ import annotations

import numpy as np
import pytest
from fixtures_logits import (
    LOGITS_FIXTURES,
    lexicon_for,
    load_fixture,
    toy_encode,
    toy_vocab_size,
)
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from zarma_numbers.generator import MAX_VALUE, generate
from zarma_numbers.grammar import load_grammar
from zarma_numbers.parser import parse

_BLANK = 0


@pytest.fixture(scope="module")
def grammar():
    return load_grammar()


@pytest.fixture(scope="module")
def decoder(decoding, grammar):
    lexicon = decoding.build_token_lexicon(
        grammar, toy_encode, separator=toy_encode(" "), blank_id=_BLANK
    )
    return decoding.ConstrainedCtcDecoder(grammar, lexicon)


# --- Validité : toute sortie est un nombre (property-based) ---


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    seed=st.integers(min_value=0, max_value=10_000),
    frames=st.integers(min_value=1, max_value=25),
)
def test_every_output_is_parseable_whatever_the_logits(decoder, grammar, seed, frames):
    logits = np.random.default_rng(seed).normal(0.0, 3.0, size=(frames, toy_vocab_size()))
    result = decoder.decode(logits)
    for hypothesis in result.hypotheses:
        assert grammar.accepts(hypothesis.text)
        value = parse(hypothesis.text)
        assert value is not None
        assert generate(value) == hypothesis.text


@settings(
    max_examples=12,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(n=st.integers(min_value=0, max_value=MAX_VALUE))
def test_clean_utterance_of_any_number_decodes_back_to_it(decoder, n):
    # Peu d'exemples : chaque nombre long produit ~250 trames à décoder. La
    # couverture exhaustive de la *grammaire* est assurée côté task 1 ; ici on
    # vérifie le bout en bout acoustique sur un échantillon de la plage.
    from fixtures_logits import clean_logits

    result = decoder.decode(clean_logits(generate(n)))
    assert result.best is not None
    assert parse(result.best.text) == n


def test_output_is_never_non_latin(decoder):
    rng = np.random.default_rng(99)
    for seed in range(5):
        logits = rng.normal(0.0, 5.0, size=(20 + seed, toy_vocab_size()))
        for hypothesis in decoder.decode(logits).hypotheses:
            assert hypothesis.text.isascii()


# --- Fixtures de logits sur disque (CI sans modèle ni GPU) ---


def test_fixtures_are_available():
    assert LOGITS_FIXTURES, "aucune fixture de logits disponible"


@pytest.mark.parametrize("name", sorted(LOGITS_FIXTURES))
def test_decodes_logits_fixture_from_disk(decoding, grammar, name):
    fixture = load_fixture(name)
    # Chaque provenance a son lexique de tokens : jouet pour les fixtures
    # synthétiques, BPE Omnilingual réel pour les logits dumpés du modèle.
    lexicon = lexicon_for(fixture, decoding, grammar)
    decoder = decoding.ConstrainedCtcDecoder(grammar, lexicon)
    result = decoder.decode(fixture.logits)

    assert result.frame_count == fixture.logits.shape[0]
    for hypothesis in result.hypotheses:
        assert grammar.accepts(hypothesis.text)

    if fixture.expected_number is not None:
        assert result.best is not None
        assert parse(result.best.text) == fixture.expected_number
        assert result.best.text == fixture.expected_prompt
    else:
        # Fixture non numérique : la confiance doit rester faible (task 3).
        assert result.confidence < 0.5


def test_real_model_fixtures_are_present():
    """La CI doit exercer le décodeur sur de **vrais** logits, pas seulement des
    tenseurs synthétiques (task 6)."""
    real = [name for name in LOGITS_FIXTURES if load_fixture(name).provenance == "model"]
    assert real, "aucune fixture de logits réels — relancer decode_constrained.py --dump-logits"
    for name in real:
        fixture = load_fixture(name)
        # Vocabulaire réel d'Omnilingual (Annexe A §2).
        assert fixture.logits.shape[1] == 10_288


def test_fixtures_carry_their_provenance():
    for name in LOGITS_FIXTURES:
        fixture = load_fixture(name)
        assert fixture.provenance in ("synthetic", "model")
        assert fixture.logits.ndim == 2
        assert fixture.logits.shape[0] > 0
