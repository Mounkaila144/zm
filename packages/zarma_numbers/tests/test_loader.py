"""Tests du chargeur de lexique (story 1.3)."""

import textwrap

import pytest
from zarma_numbers.exceptions import LexiconValidationError
from zarma_numbers.loader import load_lexicon


@pytest.fixture(scope="module")
def lexicon():
    """Charge le lexique embarqué (source de vérité du paquet)."""
    return load_lexicon()


# --- AC1 : chargement nominal, toutes les catégories présentes ---


def test_load_returns_all_categories(lexicon):
    assert lexicon.zero.canonical == "yaamo"
    assert set(lexicon.units.keys()) == set(range(1, 10))
    assert set(lexicon.tens.keys()) == set(range(10, 100, 10))
    assert {"tens_unit", "groups"} <= set(lexicon.connectors.keys())
    for required_scale in ("hundred", "thousand", "million"):
        assert required_scale in lexicon.scales


def test_units_expose_isolated_and_combined(lexicon):
    assert lexicon.units[1].isolated == "afo"
    assert lexicon.units[1].combined == "fo"
    assert lexicon.units[6].variants == ("iddou", "iddu")


def test_every_entry_has_valid_status(lexicon):
    assert lexicon.zero.status == "unresolved"
    assert all(u.status in {"validé", "unresolved"} for u in lexicon.units.values())
    assert all(t.status in {"validé", "unresolved"} for t in lexicon.tens.values())


def test_intermediate_scales_have_no_canonical(lexicon):
    # ten_thousand / hundred_thousand : composés via zambar, canonical null.
    for key in ("ten_thousand", "hundred_thousand"):
        assert lexicon.scales[key].canonical is None


def test_million_is_resolved(lexicon):
    # Story 1.7 : la forme million est désormais résolue (mais statut unresolved
    # tant que < 3 locuteurs — gate de gouvernance).
    assert lexicon.scales["million"].canonical == "million"


def test_remainder_marker_dala_loaded(lexicon):
    assert lexicon.connectors["remainder"].canonical == "dala"


# --- AC2 : grammar_version exposé ---


def test_grammar_version_is_exposed(lexicon):
    assert lexicon.grammar_version == "1.5.0"


def test_grammar_version_accessible_from_package():
    import zarma_numbers

    assert zarma_numbers.load_lexicon().grammar_version == "1.5.0"


# --- AC4 : variantes linguistiques et corrections ASR séparées ---


def test_variants_and_asr_confusions_are_separate(lexicon):
    variant_map = lexicon.linguistic_variant_map()

    # Variante linguistique légitime : présente dans la map linguistique.
    assert variant_map.get("nda") == "da"
    assert variant_map.get("iddu") == "iddou"
    assert variant_map.get("wey") == "iwey"

    # Correction ASR : présente UNIQUEMENT dans asr_confusions, jamais dans la
    # map linguistique.
    assert lexicon.asr_confusions == {"zangu": "zangou"}
    assert "zangu" not in variant_map


def test_asr_confusions_do_not_leak_into_linguistic_variants(lexicon):
    variant_map = lexicon.linguistic_variant_map()
    assert set(lexicon.asr_confusions).isdisjoint(variant_map)


# --- AC3 : échec propre sur lexique invalide / incomplet ---


def _write(tmp_path, content: str):
    path = tmp_path / "lexicon.yaml"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def test_missing_required_key_raises(tmp_path):
    path = _write(
        tmp_path,
        """
        language: dje_Latn
        status: draft
        zero: { value: 0, canonical: yaamo, variants: [yaamo], status: unresolved }
        """,
    )
    with pytest.raises(LexiconValidationError, match="version"):
        load_lexicon(path)


def test_missing_unit_raises(tmp_path):
    path = _write(
        tmp_path,
        """
        version: "1.0.0"
        language: dje_Latn
        status: draft
        zero: { value: 0, canonical: yaamo, variants: [yaamo], status: unresolved }
        units:
          1: { isolated: afo, combined: fo, variants: [afo], status: unresolved }
        tens: {}
        connectors: {}
        scales: {}
        """,
    )
    with pytest.raises(LexiconValidationError, match="Unité requise manquante"):
        load_lexicon(path)


def test_invalid_status_raises(tmp_path):
    path = _write(
        tmp_path,
        """
        version: "1.0.0"
        language: dje_Latn
        status: draft
        zero: { value: 0, canonical: yaamo, variants: [yaamo], status: WRONG }
        units: {}
        tens: {}
        connectors: {}
        scales: {}
        """,
    )
    with pytest.raises(LexiconValidationError, match="Statut invalide"):
        load_lexicon(path)


def test_missing_file_raises(tmp_path):
    with pytest.raises(LexiconValidationError, match="introuvable"):
        load_lexicon(tmp_path / "does_not_exist.yaml")


# --- Section `operators` (story 6.1) : validée, jamais devinée ---


def _with_operators(tmp_path, operators: str):
    """Lexique minimal valide, dont seule la section `operators` varie."""
    units = [
        f"  {d}: {{ isolated: u{d}, combined: c{d}, variants: [], status: unresolved }}"
        for d in range(1, 10)
    ]
    tens = [
        f"  {t}: {{ canonical: t{t}, variants: [], status: unresolved }}"
        for t in range(10, 100, 10)
    ]
    lines = [
        'version: "1.0.0"',
        "language: dje_Latn",
        "status: draft",
        "zero: { value: 0, canonical: yaamo, variants: [yaamo], status: unresolved }",
        "units:",
        *units,
        "tens:",
        *tens,
        "connectors:",
        "  tens_unit: { canonical: cindi, variants: [], status: unresolved }",
        "  groups: { canonical: da, variants: [], status: unresolved }",
        "scales:",
        "  hundred: { value: 100, canonical: zangou, variants: [], status: unresolved }",
        "  thousand: { value: 1000, canonical: zambar, variants: [], status: unresolved }",
        "  million: { value: 1000000, canonical: null, variants: [], status: unresolved }",
        "operators:",
        operators,
    ]
    path = tmp_path / "lexicon.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_operator_with_unknown_symbol_raises(tmp_path):
    path = _with_operators(
        tmp_path,
        '          add: { symbol: "%", canonical: tonton, variants: [], status: unresolved }\n',
    )
    with pytest.raises(LexiconValidationError, match="Symbole invalide"):
        load_lexicon(path)


def test_duplicate_operator_symbol_raises(tmp_path):
    path = _with_operators(
        tmp_path,
        '          add: { symbol: "+", canonical: tonton, variants: [], status: unresolved }\n'
        '          plus: { symbol: "+", canonical: autre, variants: [], status: unresolved }\n',
    )
    with pytest.raises(LexiconValidationError, match="déclaré deux fois"):
        load_lexicon(path)


def test_two_operators_sharing_a_spoken_form_raises(tmp_path):
    """Deux opérateurs homophones rendraient l'expression entendue indécidable."""
    path = _with_operators(
        tmp_path,
        '          add: { symbol: "+", canonical: tonton, variants: [], status: unresolved }\n'
        '          subtract: { symbol: "-", canonical: zabou, variants: [tonton], '
        "status: unresolved }\n",
    )
    with pytest.raises(LexiconValidationError, match="Forme d'opérateur ambiguë"):
        load_lexicon(path)


def test_lexicon_without_operators_section_still_loads(tmp_path):
    """Rétro-compatibilité : un lexique 1.2.x reste lisible (opérateurs vides)."""
    path = _with_operators(tmp_path, "          {}\n")
    assert load_lexicon(path).operators == {}
