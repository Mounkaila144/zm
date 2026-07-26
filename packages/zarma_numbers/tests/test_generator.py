"""Tests du générateur ``nombre → zarma`` (story 1.4)."""

import pytest
from zarma_numbers.exceptions import OutOfRangeError
from zarma_numbers.generator import MAX_VALUE, generate

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
        # connecteur `da` (cas général) / `di` (devant 2, 3, 4, 5, 10, avec
        # élision `iwey` → `wey`) — distribution complémentaire, correction
        # locuteur 2026-07-25.
        (101, "zangou da fo"),
        (102, "zangou di hinka"),
        (105, "zangou di gou"),
        (106, "zangou da iddu"),
        (110, "zangou di wey"),
        (115, "zangou di wey cindi gou"),
        (120, "zangou da waranka"),
        (156, "zangou da waygou cindi iddu"),
        (200, "zangou hinka"),
        (250, "zangou hinka da waygou"),
        (372, "zangou hinza da wayiyye cindi hinka"),
        (999, "zangou yega da wayyegga cindi yega"),
        # milliers (zambar + multiplicateur + reste)
        (1000, "zambar fo"),
        (1001, "zambar fo da fo"),
        (1002, "zambar fo di hinka"),
        (1010, "zambar fo di wey"),
        (1100, "zambar fo da zangou"),
        (2000, "zambar hinka"),
        (12345, "zambar iwey cindi hinka da zangou hinza da waytaci cindi gou"),
        (45678, "zambar waytaci cindi gou da zangou iddu da wayiyye cindi hakou"),
        (
            888888,
            "zambar zangou hakou da wayhakkou cindi hakou da zangou hakou da wayhakkou cindi hakou",  # noqa: E501
        ),
        (
            999999,
            "zambar zangou yega da wayyegga cindi yega da zangou yega da wayyegga cindi yega",
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
    assert generate(100_005) == "zambar zangou da dala gou"
    assert generate(105_000) == "zambar zangou di gou"
    assert generate(100_005) != generate(105_000)


# --- Extension million : même mécanisme que `zambar`, une échelle au-dessus ---


def test_million_multiplier_reuses_zambar_pattern():
    # "million <multiplicateur>" — même grammaire que "zambar <multiplicateur>",
    # le multiplicateur pouvant lui-même être un below_million complet.
    assert generate(2_000_000) == "million hinka"
    assert generate(15_000_000) == "million iwey cindi gou"
    assert generate(100_000_000) == "million zangou"


def test_million_remainder_reuses_zambar_pattern():
    # "million <connecteur> <reste>" — même sélection da/di (élision) que `zambar`,
    # le multiplicateur (1) étant omis (forme "million" déjà résolue).
    assert generate(1_000_002) == "million di hinka"
    assert generate(1_000_500) == "million da zangou gou"


def test_million_dala_disambiguates_large_scale():
    # Même condition de déclenchement que pour `zambar` (multiplicateur multiple
    # de 100, >= 100), une échelle au-dessus : ex. 100 million pile vs 100 million
    # + 5 (ambiguïté potentielle avec 105 millions).
    assert generate(100_000_005) == "million zangou da dala gou"
    assert generate(105_000_000) == "million zangou di gou"
    assert generate(100_000_005) != generate(105_000_000)


def test_max_value_is_99999_million_plus_full_remainder():
    # Borne : 99 999 millions + un reste complet (< 1 000 000) — au-delà, une
    # échelle supérieure (milliard) non lexicalisée serait requise.
    assert MAX_VALUE == 99_999 * 1_000_000 + 999_999


# --- AC3 : entrées hors plage / invalides ---


@pytest.mark.parametrize("n", [-1, -100, MAX_VALUE + 1, MAX_VALUE + 1_000_000])
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
