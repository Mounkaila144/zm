"""Tests du générateur ``nombre → zarma`` (story 1.4)."""

import pytest
from zarma_numbers.exceptions import OutOfRangeError
from zarma_numbers.generator import generate

# --- AC1/AC2 : cas nominaux exacts (formes de la spec) ---


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (0, "yaamo"),
        # unités seules → forme isolée
        (1, "afo"),
        (2, "ihinka"),
        (9, "iyega"),
        # dizaines simples
        (10, "iwey"),
        (20, "waranka"),
        (90, "wayyegga"),
        # dizaines composées (cindi) + unité combinée
        (11, "iwey cindi fo"),
        (16, "iwey cindi iddu"),
        (24, "waranka cindi taci"),
        (99, "wayyegga cindi yega"),
        # centaines (zangou + reste)
        (100, "zangou"),
        (101, "zangou nda fo"),
        (156, "zangou nda waygou cindi iddu"),
        (200, "zangou hinka"),
        (250, "zangou hinka nda waygou"),
        (372, "zangou hinza nda wayiyye cindi hinka"),
        (999, "zangou yega nda wayyegga cindi yega"),
        # milliers (zambar + multiplicateur + reste)
        (1000, "zambar fo"),
        (2000, "zambar hinka"),
        (12345, "zambar iwey cindi hinka nda zangou hinza nda waytaci cindi gou"),
        (45678, "zambar waytaci cindi gou nda zangou iddu nda wayiyye cindi hakou"),
        (
            888888,
            "zambar zangou hakou nda wayhakkou cindi hakou nda zangou hakou nda wayhakkou cindi hakou",  # noqa: E501
        ),
        (
            999999,
            "zambar zangou yega nda wayyegga cindi yega nda zangou yega nda wayyegga cindi yega",  # noqa: E501
        ),
    ],
)
def test_generate_canonical_forms(n, expected):
    assert generate(n) == expected


# --- AC4 : cas limites ---


def test_zero():
    assert generate(0) == "yaamo"


def test_ten_thousand_composes_via_zambar():
    # 10 000 = 10 milliers → composition supportée (pas de refus).
    assert generate(10_000) == "zambar iwey"


def test_hundred_thousand_composes_via_zambar():
    # 100 000 = 100 milliers → composition supportée.
    assert generate(100_000) == "zambar zangou"


def test_million_is_resolved():
    # Story 1.7 : la forme million est résolue → generate produit "million".
    assert generate(1_000_000) == "million"


def test_dala_disambiguates_large_scale():
    # Story 1.7 : reste-unité après multiplicateur multiple de 100 marqué `dala`.
    assert generate(100_005) == "zambar zangou nda dala gou"
    assert generate(105_000) == "zambar zangou nda gou"
    assert generate(100_005) != generate(105_000)


# --- AC3 : entrées hors plage / invalides ---


@pytest.mark.parametrize("n", [-1, -100, 1_000_001, 5_000_000])
def test_out_of_range_is_refused(n):
    with pytest.raises(OutOfRangeError) as excinfo:
        generate(n)
    assert excinfo.value.code == "OUT_OF_RANGE"


@pytest.mark.parametrize("bad", ["12", 12.0, None, [1], True])
def test_non_integer_is_refused(bad):
    # Pas de coercition silencieuse : type invalide → TypeError explicite.
    # (bool est un sous-type d'int mais n'est pas un nombre valide ici.)
    with pytest.raises(TypeError):
        generate(bad)


# --- Cohérence : source unique (grammar_version accessible) ---


def test_generator_uses_package_lexicon():
    import zarma_numbers

    # generate est exposé au niveau paquet.
    assert zarma_numbers.generate(24) == "waranka cindi taci"
