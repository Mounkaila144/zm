"""Tests de la grammaire des formes valides (story 5.6, task 1).

La grammaire est un **automate** dérivé du générateur : ces tests prouvent
qu'elle décrit *exactement* la langue de ``generate`` (ni plus, ni moins), que
toute chaîne acceptée est parseable, et que les prononciations alternatives ne
se mélangent jamais aux corrections ASR (FR8).
"""

import random
from functools import cache

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from zarma_numbers.generator import MAX_VALUE, generate
from zarma_numbers.grammar import build_grammar, load_grammar
from zarma_numbers.loader import load_lexicon
from zarma_numbers.parser import parse


@pytest.fixture(scope="module")
def grammar():
    return load_grammar()


# --- AC1/AC2 : l'automate décrit exactement la langue du générateur ---


@pytest.mark.parametrize(
    ("n", "form"),
    [
        (0, "yaamo"),
        (1, "afo"),
        (11, "iwey cindi fo"),
        (42, "waytaci cindi hinka"),
        (100, "zangou"),
        (101, "zangou da fo"),
        (102, "zangou di hinka"),
        (110, "zangou di wey"),
        (115, "zangou di wey cindi gou"),
        (372, "zangou hinza da wayiyye cindi hinka"),
        (1_000, "zambar fo"),
        (1_010, "zambar fo di wey"),
        (10_000, "zambar iwey"),
        (100_000, "zambar zangou"),
        (100_005, "zambar zangou da dala gou"),
        (105_000, "zambar zangou di gou"),
        (
            999_999,
            "zambar zangou yega da wayyegga cindi yega da zangou yega da wayyegga cindi yega",
        ),  # noqa: E501
        (1_000_000, "million"),
    ],
)
def test_canonical_forms_are_accepted(grammar, n, form):
    assert generate(n) == form
    assert grammar.accepts(form)


@pytest.mark.parametrize("start", [0, 999, 1_000, 99_000, 100_000, 999_000])
def test_generated_forms_accepted_on_chunks(grammar, start):
    for n in range(start, min(start + 1_000, MAX_VALUE) + 1):
        assert grammar.accepts(generate(n)), f"forme refusée pour n={n}"


@settings(
    max_examples=300,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(n=st.integers(min_value=0, max_value=MAX_VALUE))
def test_property_every_generated_form_is_accepted(grammar, n):
    assert grammar.accepts(generate(n))


def test_language_size_is_exactly_the_generator_range(grammar):
    """Comptage des chemins acceptants : l'automate ne sur-génère pas.

    L'automate est acyclique (langue finie) ; compter ses chaînes acceptées et
    trouver 1 000 001 prouve, avec l'acceptation de chaque ``generate(n)`` et
    l'injectivité du générateur (invariant), que les deux langues coïncident.
    """

    @cache
    def count(state: int) -> int:
        total = 1 if grammar.is_accepting(state) else 0
        return total + sum(count(target) for target in grammar.transitions(state).values())

    assert count(grammar.start) == MAX_VALUE + 1


# --- AC1/AC6 : invariant de validité — toute chaîne acceptée est un nombre ---


def _random_walks(grammar, count: int, seed: int = 5_6_2026):
    """Échantillonne des chaînes acceptées en marchant dans l'automate."""
    rng = random.Random(seed)
    for _ in range(count):
        state = grammar.start
        tokens: list[str] = []
        while True:
            edges = grammar.transitions(state)
            if not edges or (grammar.is_accepting(state) and rng.random() < 0.25):
                break
            token, state = rng.choice(sorted(edges.items()))
            tokens.append(token)
        if grammar.is_accepting(state):
            yield " ".join(tokens)


def test_accepted_strings_are_parseable_and_regenerate_identically(grammar):
    walks = list(_random_walks(grammar, 400))
    assert len(walks) > 100  # l'échantillonnage doit rester représentatif
    for text in walks:
        value = parse(text)
        assert value is not None, f"chaîne acceptée non parseable : {text!r}"
        assert generate(value) == text


def test_walk_stops_on_the_first_invalid_token(grammar):
    state, canonical = grammar.walk(["zangou", "zambar"])
    assert state is None
    assert canonical == ["zangou"]


# --- Asymétrie isolée / combinée ---


@pytest.mark.parametrize("form", ["afo", "ihinka", "iyega"])
def test_isolated_units_are_valid_alone(grammar, form):
    assert grammar.accepts(form)


@pytest.mark.parametrize("form", ["fo", "hinka", "yega"])
def test_combined_units_are_invalid_alone(grammar, form):
    assert not grammar.accepts(form)


@pytest.mark.parametrize(
    ("valid", "invalid"),
    [
        ("waranka cindi fo", "waranka cindi afo"),
        ("zangou da fo", "zangou da afo"),
        ("zangou di hinka", "zangou di ihinka"),
        ("zangou hinka", "zangou ihinka"),
        ("zambar fo", "zambar afo"),
    ],
)
def test_combined_form_required_in_composition(grammar, valid, invalid):
    assert grammar.accepts(valid)
    assert not grammar.accepts(invalid)


# --- Marqueur `dala` ---


def test_dala_required_when_multiplier_is_a_multiple_of_hundred(grammar):
    assert grammar.accepts("zambar zangou da dala gou")  # 100 005
    assert grammar.accepts("zambar zangou di gou")  # 105 000
    assert grammar.accepts("zambar zangou hinka da dala fo")  # 200 001


@pytest.mark.parametrize(
    "form",
    [
        "zambar fo nda dala fo",  # multiplicateur 1 : jamais de marqueur
        "zambar iwey nda dala gou",  # multiplicateur 10 : jamais de marqueur
        "zangou nda dala fo",  # marqueur hors du groupe des milliers
        "dala",
        "zambar zangou nda dala",  # marqueur sans reste
    ],
)
def test_dala_is_refused_outside_its_case(grammar, form):
    assert not grammar.accepts(form)


# --- Formes invalides / non numériques ---


@pytest.mark.parametrize(
    "form",
    [
        "",
        "cindi",
        "nda",
        "zambar",
        "zangou zangou",
        "cindi fo",
        "iwey cindi",
        "waranka waranka",
        "bonjour",
        "afo afo",
        "zambar fo nda",
        "zangou di waranka",  # `di` devant 20 : la distribution l'interdit
        "zangou da gou",  # `da` devant 5 : idem
        "wey",  # forme élidée hors contexte `di`
    ],
)
def test_invalid_sequences_are_refused(grammar, form):
    assert not grammar.accepts(form)


def test_no_non_latin_output_is_reachable_by_construction(grammar):
    # L'alphabet de l'automate est fermé : aucune écriture non latine possible.
    assert all(token.isascii() and token.islower() for token in grammar.tokens)
    assert grammar.step(grammar.start, "一") is None
    assert grammar.step(grammar.start, "٥") is None
    assert not grammar.accepts("你好")


def test_empty_input_is_not_accepted(grammar):
    assert not grammar.is_accepting(grammar.start)


# --- Prononciations alternatives (variantes linguistiques uniquement) ---


def test_alternative_pronunciations_map_to_the_canonical_form(grammar):
    # `nda` est une variante linguistique de `da` (lexique v1.2.0) ; `di` est
    # un connecteur à part entière, jamais réécrit.
    assert grammar.canonical_token("nda") == "da"
    assert grammar.canonical_token("da") == "da"
    assert grammar.canonical_token("di") == "di"
    assert grammar.canonical_form("zangou nda fo") == "zangou da fo"
    assert grammar.canonical_form("zangou da fo") == "zangou da fo"


def test_connector_distribution_is_enforced(grammar):
    # Distribution complémentaire (correction locuteur 2026-07-25) : `di`
    # devant 2, 3, 4, 5, 10 (avec élision `iwey` → `wey`), `da` partout
    # ailleurs — jamais interchangeables, même via les prononciations.
    assert grammar.canonical_form("zangou di hinka") == "zangou di hinka"
    assert grammar.canonical_form("zangou di wey") == "zangou di wey"
    assert grammar.canonical_form("zangou da hinka") is None
    assert grammar.canonical_form("zangou nda hinka") is None
    assert grammar.canonical_form("zangou di fo") is None
    assert grammar.canonical_form("zangou di iwey") is None  # élision obligatoire
    assert grammar.canonical_form("zangou da wey") is None


def test_elided_wey_is_never_rewritten(grammar):
    # `wey` (forme élidée après `di`) est un token de surface de l'automate :
    # il n'est pas réécrit vers `iwey` malgré la variante du lexique — les deux
    # gardent leur sens contextuel (`zambar iwey` = 10 000 vs `di wey`).
    assert grammar.canonical_token("wey") == "wey"
    assert grammar.canonical_token("iwey") == "iwey"
    assert grammar.accepts("zambar iwey")
    assert not grammar.accepts("zambar wey")


def test_canonical_form_returns_none_for_invalid_sequences(grammar):
    assert grammar.canonical_form("zangou da") is None
    assert grammar.canonical_form("bonjour") is None


def test_pronunciations_can_be_disabled(grammar):
    assert not grammar.accepts("zangou nda fo", allow_pronunciations=False)
    assert grammar.accepts("zangou da fo", allow_pronunciations=False)


def test_canonical_tokens_are_never_reinterpreted(grammar):
    # `fo` (combinée) et `afo` (isolée) sont deux tokens canoniques distincts :
    # aucune n'est réécrite vers l'autre, sinon le sens contextuel est perdu.
    assert grammar.canonical_token("fo") == "fo"
    assert grammar.canonical_token("afo") == "afo"


def test_asr_confusions_never_enter_the_pronunciation_table(grammar):
    # FR8 : variantes linguistiques et corrections ASR restent séparées.
    confusions = load_lexicon().asr_confusions
    assert confusions  # le lexique v1 en contient au moins une
    for wrong_form in confusions:
        assert grammar.canonical_token(wrong_form) is None
        assert not grammar.accepts(f"{wrong_form} hinka")


def test_every_token_is_its_own_pronunciation(grammar):
    for token in grammar.tokens:
        assert token in grammar.pronunciations[token]
        assert grammar.canonical_token(token) == token


# --- Source unique & structure ---


def test_grammar_version_comes_from_the_lexicon(grammar):
    assert grammar.grammar_version == load_lexicon().grammar_version


def test_automaton_stays_compact(grammar):
    # Un trie exhaustif des 1 000 001 formes serait ingérable : l'automate
    # partage ses sous-structures (AC2 — pas d'énumération).
    assert grammar.state_count < 10_000
    assert grammar.tokens


def test_build_is_deterministic_and_cached():
    first = load_grammar()
    assert load_grammar() is first
    rebuilt = build_grammar()
    assert rebuilt is not first
    assert rebuilt.state_count == first.state_count
    assert rebuilt.tokens == first.tokens
    assert dict(rebuilt.pronunciations) == dict(first.pronunciations)
