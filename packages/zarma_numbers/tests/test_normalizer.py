"""Tests du normaliseur de texte (story 1.5)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from zarma_numbers.generator import generate
from zarma_numbers.normalizer import normalize, normalize_with_trace

# --- AC1/AC2 : variantes orthographiques → forme canonique ---


def test_connector_variant_nda_to_da():
    # Depuis le lexique 1.2.0, la forme canonique du connecteur général est
    # `da` ; `nda` en est la variante linguistique.
    assert normalize("nda") == "da"


def test_connector_variant_in_expression():
    assert normalize("zangou hinka nda waygou") == "zangou hinka da waygou"
    assert normalize("zambar fo nda zangou") == "zambar fo da zangou"


# --- AC1 : casse et espaces ---


def test_case_and_whitespace():
    assert normalize("  Zambar   FO  ") == "zambar fo"


def test_punctuation_removed():
    assert normalize("zangou, hinka!") == "zangou hinka"


def test_canonical_forms_are_preserved():
    # Les formes canoniques (isolée ET combinée) ne sont jamais réécrites.
    assert normalize("fo") == "fo"  # combinée de 1, PAS remappée vers "afo"
    assert normalize("afo") == "afo"
    assert normalize("da") == "da"
    assert normalize("di") == "di"  # connecteur élidé : canonique, jamais réécrit


# --- AC3 : idempotence ---


@pytest.mark.parametrize(
    "text",
    [
        "",
        "da",
        "Zambar FO da zangou",
        "  waranka   cindi  taci ",
        "un texte non numerique quelconque",
        "zangou, hinka! da waygou.",
        generate(12345),
        generate(999999),
    ],
)
def test_idempotence(text):
    once = normalize(text)
    assert normalize(once) == once


@given(st.text())
def test_idempotence_property(text):
    once = normalize(text)
    assert normalize(once) == once


def test_normalize_does_not_corrupt_generator_output():
    # Normaliser une sortie canonique du générateur la laisse inchangée.
    for n in (0, 24, 372, 1000, 12345):
        assert normalize(generate(n)) == generate(n)


# --- AC4 : entrées non numériques non « corrigées » ---


def test_non_numeric_text_is_cleaned_not_corrected():
    # Nettoyage (casse/ponctuation) mais aucun rapprochement vers un nombre.
    assert normalize("Bonjour, le Monde!") == "bonjour le monde"


def test_unknown_token_left_as_is():
    assert normalize("xyzzy") == "xyzzy"


# --- AC2 : paires de confusion préservées (pas de fuzzy matching) ---


def test_confusion_pair_hinka_hinza_preserved():
    assert normalize("hinka") == "hinka"
    assert normalize("hinza") == "hinza"
    assert normalize("hinka") != normalize("hinza")


# --- Task 4 : trace typée + séparation stricte (pas d'asr_confusions) ---


def test_trace_records_linguistic_variant():
    result = normalize_with_trace("Zambar fo nda zangou")
    assert result.raw == "Zambar fo nda zangou"
    assert result.normalized == "zambar fo da zangou"
    assert len(result.transformations) == 1
    tr = result.transformations[0]
    assert (tr.source, tr.target, tr.kind) == ("nda", "da", "linguistic_variant")
    assert tr.as_dict() == {"from": "nda", "to": "da", "type": "linguistic_variant"}


def test_asr_confusion_not_applied_by_normalizer():
    # "zangu" est une correction ASR (asr_confusions), PAS une variante
    # linguistique → le normaliseur ne doit pas la corriger.
    assert normalize("zangu") == "zangu"
    result = normalize_with_trace("zangu")
    assert result.transformations == []


# --- Robustesse ---


def test_non_string_input_raises():
    with pytest.raises(TypeError):
        normalize(123)


def test_empty_string():
    assert normalize("") == ""
    assert normalize("   ") == ""


# --- Formes élidées : comportement assumé (lexique 1.2.0) ---


def test_elided_form_is_remapped_to_the_declared_canonical():
    """``wey`` (élision de ``iwey`` après ``di``) est remappé — choix assumé.

    Les deux graphies sont linguistiquement valables et désignent la même valeur
    (10) ; la protection ne couvre que les formes **déclarées** au lexique, et
    ``wey`` n'y figure que comme variante. Ce test épingle le comportement pour
    qu'il reste un choix explicite.
    """
    assert normalize("zangou di wey") == "zangou di iwey"
    assert normalize("wey") == "iwey"


def test_elided_form_keeps_the_invariant_intact():
    # Ce qui compte est préservé : la valeur analysée reste la bonne.
    import zarma_numbers

    for n in (110, 115, 1110, 100_010):
        assert zarma_numbers.parse(normalize(zarma_numbers.generate(n))) == n


def test_normalize_output_is_not_meant_for_the_grammar_automaton():
    """Garde-fou : la grammaire attend la sortie du **générateur**.

    Elle n'admet qu'une forme de surface par nombre — c'est ce qui rend le
    décodage contraint déterministe. Enchaîner ``normalize()`` puis
    ``grammar.accepts()`` est donc une erreur d'usage, épinglée ici pour que le
    couplage soit visible plutôt que découvert en production.
    """
    from zarma_numbers.generator import generate
    from zarma_numbers.grammar import load_grammar

    grammar = load_grammar()
    canonical = generate(110)
    assert grammar.accepts(canonical)
    assert not grammar.accepts(normalize(canonical))
