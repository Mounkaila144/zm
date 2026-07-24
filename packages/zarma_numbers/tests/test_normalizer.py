"""Tests du normaliseur de texte (story 1.5)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from zarma_numbers.generator import generate
from zarma_numbers.normalizer import normalize, normalize_with_trace

# --- AC1/AC2 : variantes orthographiques → forme canonique ---


def test_connector_variant_da_to_nda():
    assert normalize("da") == "nda"


def test_connector_variant_in_expression():
    assert normalize("zangou hinka da waygou") == "zangou hinka nda waygou"
    assert normalize("zambar fo da zangou") == "zambar fo nda zangou"


# --- AC1 : casse et espaces ---


def test_case_and_whitespace():
    assert normalize("  Zambar   FO  ") == "zambar fo"


def test_punctuation_removed():
    assert normalize("zangou, hinka!") == "zangou hinka"


def test_canonical_forms_are_preserved():
    # Les formes canoniques (isolée ET combinée) ne sont jamais réécrites.
    assert normalize("fo") == "fo"  # combinée de 1, PAS remappée vers "afo"
    assert normalize("afo") == "afo"
    assert normalize("nda") == "nda"


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
    result = normalize_with_trace("Zambar fo da zangou")
    assert result.raw == "Zambar fo da zangou"
    assert result.normalized == "zambar fo nda zangou"
    assert len(result.transformations) == 1
    tr = result.transformations[0]
    assert (tr.source, tr.target, tr.kind) == ("da", "nda", "linguistic_variant")
    assert tr.as_dict() == {"from": "da", "to": "nda", "type": "linguistic_variant"}


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
