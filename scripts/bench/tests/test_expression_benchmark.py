"""Corpus et mesure des expressions (story 6.1, tasks 5 et 8).

Deux garanties se testent ici :

- le **plan d'enregistrement** demande des énoncés complets, couvre les
  opérateurs résolus × longueurs d'opérandes, inclut des cas hors domaine, et
  n'invente jamais un opérateur non validé ;
- l'**Exact Expression Accuracy** est tout-ou-rien, et un refus attendu compte
  comme réussi seulement s'il porte le bon motif.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

import pytest
import zarma_numbers
from app.asr.base import AsrResult
from app.config import get_settings
from benchmark_corpus import (
    ManifestEntry,
    build_expression_recording_plan,
    build_manifest,
    expression_plan_dict,
    read_manifest,
    select_target_expressions,
    validate_manifest,
    write_manifest,
)
from evaluation import build_report, evaluate, report_to_markdown
from zarma_numbers.expressions import Expression, render_expression

SPEAKERS = ("spk01", "spk02", "spk03")


def lexicon_without(tmp_path: Path, names: Sequence[str]) -> Path:
    """Copie du lexique où les opérateurs ``names`` redeviennent non résolus.

    Les quatre sont validés au lexique livré ; simuler l'absence est le seul
    moyen de continuer à prouver que l'outillage **refuse** plutôt qu'il devine.
    """
    source = Path(zarma_numbers.__file__).parent / "lexicon.yaml"
    text = source.read_text(encoding="utf-8")
    for name in names:
        pattern = rf'(?m)^(  {name}: \{{ symbol: "[^"]+", canonical: )[^,]+'
        updated = re.sub(pattern, r"\1null", text)
        assert updated != text, f"opérateur '{name}' introuvable dans le lexique"
        text = updated
    path = tmp_path / "stripped.yaml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def engine_without_division(tmp_path, monkeypatch):
    """Moteur d'expressions privé de la division (lexique simulé)."""
    from zarma_numbers import expressions

    path = lexicon_without(tmp_path, ["divide"])
    monkeypatch.setattr(expressions, "load_lexicon", lambda: zarma_numbers.load_lexicon(path))
    expressions._table.cache_clear()
    try:
        yield
    finally:
        expressions._table.cache_clear()


def asr_source_for(texts: dict[str, str]):
    """Source ASR de test : ``audio_path -> texte transcrit`` (aucun modèle)."""

    def source(entry: ManifestEntry) -> AsrResult:
        return AsrResult(
            text=texts.get(entry.audio_path, ""),
            acoustic_score=0.95,
            candidates=[],
            latency_ms=42,
            model_version="test-1.0.0",
        )

    return source


def expression_entry(
    audio_path: str,
    spec: str,
    *,
    speaker: str = "spk01",
    condition: str = "calme",
) -> dict:
    return {
        "audio_path": audio_path,
        "speaker": speaker,
        "expected_expression": spec,
        "condition": condition,
    }


# --------------------------------------------------------------------------- #
# Task 5 — plan d'enregistrement d'expressions
# --------------------------------------------------------------------------- #


def test_targets_cover_the_four_operators():
    """Depuis le lexique 1.4.0, les quatre opérations sont enregistrables."""
    specs = [target.spec for target in select_target_expressions()]
    for symbol in ("+", "-", "*", "/"):
        assert any(symbol in spec for spec in specs)


def test_an_unresolved_operator_is_never_planned(tmp_path):
    """On ne demande pas d'enregistrer une opération qu'on ne sait pas prononcer."""
    lexicon = zarma_numbers.load_lexicon(lexicon_without(tmp_path, ["divide"]))
    specs = [target.spec for target in select_target_expressions(lexicon)]
    assert specs
    assert not any("/" in spec for spec in specs)
    assert any("*" in spec for spec in specs)


def test_targets_cover_short_and_long_operands():
    tags = {tag for target in select_target_expressions() for tag in target.tags}
    assert {"short", "long"} <= tags


def test_targets_include_out_of_domain_cases():
    """Sans cas impossibles, le taux de refus correct ne se mesure pas."""
    targets = select_target_expressions()
    refusals = {t.expected_refusal for t in targets if t.expected_refusal}
    assert "NEGATIVE_RESULT" in refusals
    assert "RESULT_OVERFLOW" in refusals


def test_targets_are_deterministic():
    first = [t.spec for t in select_target_expressions()]
    second = [t.spec for t in select_target_expressions()]
    assert first == second


def test_plan_asks_for_complete_utterances():
    """La consigne est une phrase entière, jamais un opérateur isolé."""
    plan = build_expression_recording_plan(select_target_expressions(), SPEAKERS)
    for item in plan:
        assert len(item.expected_prompt.split()) >= 3


def test_plan_covers_every_speaker_and_both_conditions():
    plan = build_expression_recording_plan(select_target_expressions(), SPEAKERS)
    assert {item.speaker for item in plan} == set(SPEAKERS)
    assert {item.condition for item in plan} == {"calme", "bruit"}


def test_plan_dict_carries_the_ground_truth():
    plan = build_expression_recording_plan(select_target_expressions(), SPEAKERS)
    record = expression_plan_dict(plan[0])
    assert set(record) >= {
        "speaker",
        "expected_expression",
        "expected_prompt",
        "expected_number",
        "expected_refusal",
        "condition",
        "tags",
    }


# --------------------------------------------------------------------------- #
# Manifest : la vérité terrain est recalculée, jamais crue sur parole
# --------------------------------------------------------------------------- #


def test_manifest_carries_expression_truth(tmp_path):
    result = build_manifest([expression_entry("a.wav", "23+15")])
    assert result.written
    entry = result.entries[0]
    assert entry.is_expression
    assert entry.expected_number == 38
    assert entry.expected_prompt == render_expression(Expression(23, "+", 15))

    path = tmp_path / "manifest.jsonl"
    write_manifest(path, result.entries)
    assert read_manifest(path)[0] == entry


def test_manifest_records_the_expected_refusal():
    entry = build_manifest([expression_entry("a.wav", "3-5")]).entries[0]
    assert entry.expected_number is None
    assert entry.expected_refusal == "NEGATIVE_RESULT"


def test_manifest_rejects_an_unresolved_operator(engine_without_division):
    """Aucune consigne pour une opération qu'on ne sait pas prononcer."""
    result = build_manifest([expression_entry("a.wav", "40/8")])
    assert not result.written
    assert result.errors[0].reason == "operator_unresolved"


def test_manifest_accepts_a_division_now_that_it_is_resolved():
    entry = build_manifest([expression_entry("a.wav", "103/5")]).entries[0]
    assert entry.expected_number == 20
    assert entry.expected_remainder == 3


def test_manifest_rejects_an_unreadable_specification():
    result = build_manifest([expression_entry("a.wav", "vingt-trois plus quinze")])
    assert not result.written
    assert result.errors[0].reason == "expected_expression_invalid"


def test_number_only_manifest_is_unchanged(tmp_path):
    """Non-régression 5.1 : une entrée « nombre seul » sérialise à l'identique."""
    result = build_manifest(
        [{"audio_path": "n.wav", "speaker": "spk01", "expected_number": 42, "condition": "calme"}]
    )
    path = tmp_path / "manifest.jsonl"
    write_manifest(path, result.entries)
    record = path.read_text(encoding="utf-8")
    assert "expected_expression" not in record


def test_validate_manifest_detects_a_falsified_truth():
    """Un manifest dont le résultat a été trafiqué doit être signalé."""
    entry = build_manifest([expression_entry("a.wav", "23+15")]).entries[0]
    falsified = ManifestEntry(
        audio_path=entry.audio_path,
        expected_number=99,  # faux
        expected_prompt=entry.expected_prompt,
        speaker_key=entry.speaker_key,
        region=None,
        condition=entry.condition,
        split=entry.split,
        expected_expression=entry.expected_expression,
    )
    report = validate_manifest([falsified], min_audios=1, min_speakers=1, required_tags=())
    assert any(problem.startswith("expression_truth_mismatch") for problem in report.problems)


# --------------------------------------------------------------------------- #
# Task 8 — Exact Expression Accuracy
# --------------------------------------------------------------------------- #


def _evaluate(specs: dict[str, str], transcriptions: dict[str, str]):
    entries = build_manifest([expression_entry(path, spec) for path, spec in specs.items()]).entries
    return evaluate(entries, asr_source_for(transcriptions), get_settings())


def test_a_fully_correct_expression_counts():
    result = _evaluate(
        {"a.wav": "23+15"},
        {"a.wav": render_expression(Expression(23, "+", 15))},
    )
    assert result.exact_expression_accuracy == 1.0
    assert result.expression_correct == 1


def test_a_single_wrong_operand_fails_the_whole_expression():
    """Le cœur de la métrique : reconnaître « 23 » dans « 23 + 15 » ne vaut rien."""
    result = _evaluate(
        {"a.wav": "23+15"},
        {"a.wav": render_expression(Expression(23, "+", 16))},
    )
    assert result.exact_expression_accuracy == 0.0


def test_a_wrong_operator_fails_the_whole_expression():
    result = _evaluate(
        {"a.wav": "23+15"},
        {"a.wav": render_expression(Expression(23, "-", 15))},
    )
    assert result.exact_expression_accuracy == 0.0


def test_a_number_heard_instead_of_an_expression_fails():
    result = _evaluate({"a.wav": "23+15"}, {"a.wav": zarma_numbers.generate(38)})
    assert result.exact_expression_accuracy == 0.0
    assert result.entries[0].recognized_expression is None


def test_metrics_are_broken_down_by_operator_and_length():
    result = _evaluate(
        {
            "a.wav": "23+15",
            "b.wav": "23-15",
            "c.wav": "1234+6",
        },
        {
            "a.wav": render_expression(Expression(23, "+", 15)),
            "b.wav": render_expression(Expression(23, "-", 15)),
            "c.wav": render_expression(Expression(1234, "+", 5)),  # faux
        },
    )
    assert result.by_operator["add"].total == 2
    assert result.by_operator["add"].correct == 1
    assert result.by_operator["subtract"].accuracy == 1.0
    assert result.by_operand_length["long"].accuracy == 0.0
    assert result.by_operand_length["short"].accuracy == 1.0


def test_a_correct_refusal_counts_as_correct():
    result = _evaluate(
        {"a.wav": "3-5"},
        {"a.wav": render_expression(Expression(3, "-", 5))},
    )
    assert result.refusals.total == 1
    assert result.refusals.correct_rate == 1.0
    assert result.refusals.invented_rate == 0.0
    assert result.exact_expression_accuracy == 1.0


def test_an_invented_result_on_an_impossible_case_is_counted():
    """La défaillance la plus grave doit être visible, pas noyée."""
    result = _evaluate(
        {"a.wav": "3-5"},
        {"a.wav": render_expression(Expression(5, "-", 3))},  # entendu à l'envers
    )
    assert result.refusals.invented_rate == 1.0
    assert result.exact_expression_accuracy == 0.0


def test_report_exposes_the_expression_metrics(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    entries = build_manifest(
        [expression_entry("a.wav", "23+15"), expression_entry("b.wav", "3-5")]
    ).entries
    write_manifest(manifest, entries)

    result = evaluate(
        entries,
        asr_source_for(
            {
                "a.wav": render_expression(Expression(23, "+", 15)),
                "b.wav": render_expression(Expression(3, "-", 5)),
            }
        ),
        get_settings(),
    )
    report = build_report(
        result,
        manifest_path=manifest,
        settings=get_settings(),
        asr_mode="replay",
        latency_source="replay",
        split="test",
        timestamp="2026-07-25T00:00:00+00:00",
    )

    metrics = report["metrics"]
    assert metrics["exact_expression_accuracy"] == 1.0
    assert metrics["refusals"]["correct_rate"] == 1.0

    markdown = report_to_markdown(report)
    assert "Exact Expression Accuracy" in markdown
    assert "Par opérateur" in markdown
    assert "résultat inventé" in markdown


def test_number_only_report_still_mentions_the_metric_at_zero():
    """Une métrique absente se lirait comme une mesure oubliée."""
    entries = build_manifest(
        [{"audio_path": "n.wav", "speaker": "spk01", "expected_number": 42, "condition": "calme"}]
    ).entries
    result = evaluate(
        entries,
        asr_source_for({"n.wav": zarma_numbers.generate(42)}),
        get_settings(),
    )
    assert result.accuracy == 1.0
    assert result.exact_expression_accuracy == 0.0
    assert result.expression_total == 0


@pytest.mark.parametrize("spec", ["23+15", "3-5", "105+7"])
def test_manifest_round_trip_is_stable(tmp_path, spec):
    entries = build_manifest([expression_entry("a.wav", spec)]).entries
    path = tmp_path / "m.jsonl"
    write_manifest(path, entries)
    assert read_manifest(path) == entries
