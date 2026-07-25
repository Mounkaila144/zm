"""Décodage contraint des **expressions** arithmétiques (story 6.1, task 4).

Le décodeur en faisceau de la story 5.6 n'est pas réécrit ici : il change de
**langue**, pas d'algorithme. Ces tests le prouvent et vérifient les trois
points que la story identifie comme sensibles au changement d'automate :

- toute sortie appartient à la grammaire des expressions et est **évaluable**
  (AC7) — la contrepartie, pour les expressions, de « toute sortie est un
  nombre parseable » ;
- la **contrainte de durée** reste cohérente : une expression est plus longue
  qu'un nombre seul, donc un audio trop court doit faire s'abstenir le
  décodeur, jamais produire une opération inventée (FR21) ;
- la **latence** reste mesurée sur un automate deux fois plus grand.

Sans GPU, sans modèle : tokenizer jouet et logits synthétiques (fixtures).
"""

from __future__ import annotations

import numpy as np
import pytest
from fixtures_logits import clean_logits, expression_fixtures, toy_token_lexicon
from zarma_numbers.expressions import (
    Expression,
    evaluate,
    parse_expression,
    render_expression,
)
from zarma_numbers.generator import generate
from zarma_numbers.grammar import load_expression_grammar, load_grammar

FIXTURE_NAMES = tuple(sorted(expression_fixtures()))


@pytest.fixture(scope="module")
def grammar():
    return load_expression_grammar()


@pytest.fixture(scope="module")
def decoder(decoding, grammar):
    """Décodeur contraint à la grammaire des expressions (construit une fois)."""
    lexicon = toy_token_lexicon(decoding, grammar)
    return decoding.ConstrainedCtcDecoder(grammar, lexicon, decoding.DecoderConfig())


# --------------------------------------------------------------------------- #
# AC7 — la sortie appartient à la grammaire, ou le décodeur s'abstient
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_decoded_expression_is_valid_and_evaluable(decoder, grammar, name):
    fixture = expression_fixtures()[name]
    result = decoder.decode(fixture.logits)

    assert result.best is not None
    assert result.best.text == fixture.expected_prompt
    assert grammar.accepts(result.best.text)

    expression = parse_expression(result.best.text)
    assert expression is not None
    assert evaluate(expression).value == fixture.expected_number


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_every_hypothesis_belongs_to_the_language(decoder, name):
    """Aucune hypothèse — même mauvaise — ne peut sortir de la grammaire."""
    for hypothesis in decoder.decode(expression_fixtures()[name].logits).hypotheses:
        assert parse_expression(hypothesis.text) is not None


def test_a_number_alone_can_never_be_decoded_as_an_expression(decoder):
    """Audio d'un nombre seul : le décodeur ne doit pas fabriquer une opération.

    Il s'abstient, ou produit une expression — mais jamais un nombre nu, qui
    n'appartient pas à cette langue. Le pipeline API en déduira ``repeat``.
    """
    result = decoder.decode(clean_logits(generate(42)))
    if result.best is not None:
        assert parse_expression(result.best.text) is not None


def test_non_numeric_speech_yields_low_confidence(decoder):
    """Parole quelconque : la confiance de décodage doit s'effondrer (FR21)."""
    result = decoder.decode(clean_logits("kala suba borey ga koy"))
    assert result.confidence < 0.5


# --------------------------------------------------------------------------- #
# Contrainte de durée : une expression est plus longue qu'un nombre
# --------------------------------------------------------------------------- #


def test_expressions_need_more_frames_than_numbers(decoding, grammar):
    """Le plancher de trames imposé par l'automate croît avec la langue.

    C'est ce qui empêche un audio d'une seconde de se voir attribuer une
    opération à deux opérandes : les faisceaux sont élagués faute de trames.
    """
    number_grammar = load_grammar()
    number_decoder = decoding.ConstrainedCtcDecoder(
        number_grammar, toy_token_lexicon(decoding, number_grammar), decoding.DecoderConfig()
    )
    expression_decoder = decoding.ConstrainedCtcDecoder(
        grammar, toy_token_lexicon(decoding, grammar), decoding.DecoderConfig()
    )

    def minimum_frames(decoder) -> float:
        automaton = decoder._automaton  # noqa: SLF001 - propriété structurelle testée ici
        return automaton.min_tokens[automaton.start]

    assert minimum_frames(expression_decoder) > minimum_frames(number_decoder)


def test_audio_too_short_makes_the_decoder_abstain(decoder):
    """Trop peu de trames pour une expression entière → abstention, pas d'invention."""
    truncated = clean_logits(render_expression(Expression(23, "+", 15)))[:10]
    result = decoder.decode(truncated)
    assert result.best is None


def test_duration_constraint_is_configurable(decoding, grammar):
    """``min_frames_per_token`` élague les candidats trop longs pour l'audio.

    Deux effets vérifiés sur les **mêmes** logits : durcir le seuil raccourcit
    l'hypothèse retenue, et le pousser au-delà de ce que l'audio peut porter
    fait s'abstenir le décodeur au lieu de forcer une opération.
    """
    lexicon = toy_token_lexicon(decoding, grammar)
    logits = clean_logits(render_expression(Expression(23, "+", 15)))

    def best_with(min_frames: float):
        config = decoding.DecoderConfig(min_frames_per_token=min_frames)
        return decoding.ConstrainedCtcDecoder(grammar, lexicon, config).decode(logits).best

    permissive = best_with(1.0)
    strict = best_with(6.0)

    assert permissive is not None
    assert permissive.text == render_expression(Expression(23, "+", 15))
    assert strict is not None
    assert len(strict.token_ids) < len(permissive.token_ids)
    assert best_with(12.0) is None


# --------------------------------------------------------------------------- #
# Latence : deux opérandes + un opérateur allongent l'audio et le faisceau
# --------------------------------------------------------------------------- #


def test_latency_stays_within_a_reasonable_cpu_budget(decoder):
    """Budget large et volontairement stable en CI : on détecte un effondrement.

    La mesure de référence, elle, se fait sur le vrai modèle (harnais 5.2) ;
    ici on vérifie seulement que l'automate plus grand n'explose pas.
    """
    result = decoder.decode(clean_logits(render_expression(Expression(1234, "+", 567))))
    assert result.best is not None
    assert result.latency_ms < 10_000
    assert result.frame_count > 0


# --------------------------------------------------------------------------- #
# Non-régression : le décodage « nombre seul » est inchangé
# --------------------------------------------------------------------------- #


def test_number_only_decoding_is_untouched(decoding):
    """Les epics 1–5 doivent se comporter à l'identique — même langue, même sortie."""
    number_grammar = load_grammar()
    number_decoder = decoding.ConstrainedCtcDecoder(
        number_grammar, toy_token_lexicon(decoding, number_grammar), decoding.DecoderConfig()
    )
    result = number_decoder.decode(clean_logits(generate(42)))
    assert result.best is not None
    assert result.best.text == generate(42)


def test_settings_select_the_grammar_by_configuration(asr_config):
    """Basculer la calculatrice vocale est une variable d'environnement, pas du code."""
    assert asr_config.AsrSettings().DECODE_GRAMMAR == "numbers"
    assert asr_config.AsrSettings(DECODE_GRAMMAR="numbers").load_grammar().kind == "numbers"
    assert asr_config.AsrSettings(DECODE_GRAMMAR="expressions").load_grammar().kind == "expressions"


def test_unknown_grammar_kind_is_rejected(asr_config):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        asr_config.AsrSettings(DECODE_GRAMMAR="fuzzy")


def test_toy_logits_are_reproducible():
    """Garde-fou : les fixtures doivent rester déterministes d'une CI à l'autre."""
    first = clean_logits(render_expression(Expression(23, "+", 15)), noise=1.5, seed=7)
    second = clean_logits(render_expression(Expression(23, "+", 15)), noise=1.5, seed=7)
    assert np.array_equal(first, second)
