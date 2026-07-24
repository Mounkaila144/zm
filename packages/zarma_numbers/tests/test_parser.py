"""Tests du parseur ``zarma → nombre`` (story 1.6)."""

import pytest
from zarma_numbers.generator import generate
from zarma_numbers.parser import parse, parse_detailed

# --- AC1 : reparse exact des formes canoniques du générateur ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("yaamo", 0),
        ("ihinka", 2),
        ("iwey", 10),
        ("waranka cindi taci", 24),
        ("wayyegga cindi yega", 99),
        ("zangou", 100),
        ("zangou nda fo", 101),
        ("zangou hinka nda waygou", 250),
        ("zangou hinza nda wayiyye cindi hinka", 372),
        ("zambar fo", 1000),
        ("zambar iwey cindi hinka nda zangou hinza nda waytaci cindi gou", 12345),
        ("zambar waytaci cindi gou nda zangou iddu nda wayiyye cindi hakou", 45678),
    ],
)
def test_parse_canonical_forms(text, expected):
    assert parse(text) == expected


@pytest.mark.parametrize("n", [0, 1, 9, 10, 24, 99, 100, 372, 999, 1000, 12345, 99999])
def test_roundtrip_matches_generator(n):
    assert parse(generate(n)) == n


# --- AC2 : jamais inventer un nombre ---


@pytest.mark.parametrize("text", ["", "   ", "bonjour le monde", "xyzzy", "foobar test"])
def test_non_numeric_returns_none(text):
    assert parse(text) is None


def test_empty_input_error_code():
    assert parse_detailed("").error_code == "EMPTY_INPUT"
    assert parse_detailed("   ").error_code == "EMPTY_INPUT"


def test_non_numeric_speech_error_code():
    result = parse_detailed("bonjour le monde")
    assert result.accepted is False
    assert result.best is None
    assert result.error_code == "NON_NUMERIC_SPEECH"


def test_unknown_token_after_number():
    assert parse("waranka bonjour") is None
    assert parse_detailed("waranka bonjour").error_code == "UNKNOWN_TOKEN"


def test_invalid_token_order():
    # 'cindi' en tête = ordre invalide.
    assert parse("cindi taci") is None
    assert parse_detailed("cindi taci").error_code == "INVALID_TOKEN_ORDER"


def test_cindi_without_unit():
    assert parse("waranka cindi") is None
    assert parse_detailed("waranka cindi").error_code == "INVALID_TOKEN_ORDER"


def test_zambar_without_multiplier():
    assert parse_detailed("zambar").error_code == "MISSING_MULTIPLIER"


def test_duplicate_scale():
    assert parse_detailed("zambar fo zambar").error_code == "DUPLICATE_SCALE"


# --- AC4 : paires de confusion distinctes (aucun rapprochement) ---


def test_confusion_pairs_are_distinct():
    assert parse("hinka") == 2  # 2 combiné
    assert parse("hinza") == 3  # 3 combiné
    assert parse("iyye") == 7
    assert parse("yega") == 9
    assert parse("iddu") == 6
    # Toutes distinctes deux à deux.
    values = {parse(t) for t in ("hinka", "hinza", "iyye", "yega", "iddu")}
    assert values == {2, 3, 7, 9, 6}


def test_no_fuzzy_matching_on_near_miss():
    # "hinko" n'existe pas : ne doit PAS être rapproché de hinka/hinza.
    assert parse("hinko") is None


# --- Interface détaillée ---


def test_parse_detailed_accepted():
    result = parse_detailed("waranka cindi taci")
    assert result.accepted is True
    assert result.best is not None
    assert result.best.value == 24
    assert result.error_code is None


def test_parse_normalizes_internally():
    # Casse + variante 'da' + espaces : parse normalise en interne.
    assert parse("  Zangou   Hinka  da  Waygou  ") == 250


# --- Story 1.7 : dala + million ---


def test_parse_million():
    assert parse("million") == 1_000_000


def test_parse_dala_remainder():
    # dala marque le reste-unité → 100 005 (pas 105 000).
    assert parse("zambar zangou nda dala gou") == 100_005
    # sans dala → multiplicateur 105 → 105 000.
    assert parse("zambar zangou nda gou") == 105_000


def test_dala_variant_da_dala():
    # Forme native « da dala » (da = variante de nda) doit aussi parser.
    assert parse("zambar zangou da dala gou") == 100_005
