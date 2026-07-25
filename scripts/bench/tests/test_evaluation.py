"""Tests du harnais d'évaluation (story 5.2) — sans GPU, sans réseau (rejeu)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import zarma_numbers
from app.asr.base import AsrResult
from app.config import get_settings
from app.pipeline.recognition import run_recognition_pipeline
from benchmark_corpus import ManifestEntry, speaker_key_for, write_manifest
from evaluation import (
    build_report,
    evaluate,
    load_hypotheses,
    replay_source,
    report_to_json,
    write_report,
)

SETTINGS = get_settings()
# Lexique de test : rend 2 et 3 mutuellement confusables (ihinka ↔ ihinza).
LEXICON = dataclasses.replace(zarma_numbers.load_lexicon(), asr_confusions={"ihinka": "ihinza"})


def _entry(audio_path: str, number: int, *, condition="calme", split="test") -> ManifestEntry:
    return ManifestEntry(
        audio_path=audio_path,
        expected_number=number,
        expected_prompt=zarma_numbers.generate(number),
        speaker_key=speaker_key_for(audio_path),
        region=None,
        condition=condition,
        split=split,
    )


def _asr(text: str, *, score: float = 1.0, latency_ms: int = 50) -> AsrResult:
    return AsrResult(
        text=text,
        acoustic_score=score,
        candidates=[],
        latency_ms=latency_ms,
        model_version="mock-1.0.0",
    )


def _hyp(text: str, **kwargs) -> AsrResult:
    return _asr(text, **kwargs)


# --------------------------------------------------------------------------- #
# Task 1 — cœur pur (non-régression du refactor)
# --------------------------------------------------------------------------- #


def test_pure_pipeline_exact_and_reject() -> None:
    exact = run_recognition_pipeline(_asr(zarma_numbers.generate(5)), SETTINGS)
    assert exact.number == 5
    assert exact.decision == "accept"

    rejected = run_recognition_pipeline(_asr("texte non numerique"), SETTINGS)
    assert rejected.number is None
    assert rejected.decision == "repeat"


# --------------------------------------------------------------------------- #
# Task 2 — accuracy et ventilations
# --------------------------------------------------------------------------- #


def _mini_corpus() -> tuple[list[ManifestEntry], dict[str, AsrResult]]:
    entries = [
        _entry("a.wav", 5, condition="calme"),  # exact
        _entry("b.wav", 100, condition="bruit"),  # exact (long + confusion via zangou? non ici)
        _entry("c.wav", 2, condition="calme"),  # confusion : prédit 3
        _entry("d.wav", 7, condition="bruit"),  # rejet (texte non numérique)
    ]
    hypotheses = {
        "a.wav": _hyp(zarma_numbers.generate(5), latency_ms=40),
        "b.wav": _hyp(zarma_numbers.generate(100), latency_ms=60),
        "c.wav": _hyp(zarma_numbers.generate(3), latency_ms=80),  # ihinza → 3 (faux)
        "d.wav": _hyp("blabla", latency_ms=100),  # non numérique → repeat
    }
    return entries, hypotheses


def test_exact_number_accuracy_and_breakdowns() -> None:
    entries, hyp = _mini_corpus()
    result = evaluate(entries, replay_source(hyp), SETTINGS, lexicon=LEXICON)
    assert result.total == 4
    assert result.correct == 2  # a et b corrects, c faux, d rejet
    assert result.accuracy == 0.5
    # Ventilation par condition.
    assert result.by_condition["calme"].total == 2
    assert result.by_condition["calme"].correct == 1  # a correct, c faux
    assert result.by_condition["bruit"].correct == 1  # b correct, d rejet
    # Ventilation par tag (short/long/confusion).
    assert "short" in result.by_tag and "long" in result.by_tag
    assert result.by_split["test"].total == 4


def test_decision_rates() -> None:
    entries, hyp = _mini_corpus()
    result = evaluate(entries, replay_source(hyp), SETTINGS, lexicon=LEXICON)
    rates = result.decision_rates
    assert rates.rejection_rate == 0.25  # 1 repeat / 4
    assert rates.false_acceptance_rate == 0.25  # c : accept mais faux
    assert rates.correct_acceptance_rate == 0.5  # a, b


def test_latency_aggregates() -> None:
    entries, hyp = _mini_corpus()
    result = evaluate(entries, replay_source(hyp), SETTINGS, lexicon=LEXICON)
    assert result.latency["count"] == 4
    assert result.latency["min_ms"] == 40
    assert result.latency["max_ms"] == 100


# --------------------------------------------------------------------------- #
# Task 3 — matrice de confusions & paires proches
# --------------------------------------------------------------------------- #


def test_confusion_matrix_marks_known_close_pair() -> None:
    entries, hyp = _mini_corpus()
    result = evaluate(entries, replay_source(hyp), SETTINGS, lexicon=LEXICON)
    # La seule paire hors diagonale est (2 attendu, 3 prédit).
    pairs = {(p.expected_number, p.predicted_number): p for p in result.confusion_pairs}
    assert (2, 3) in pairs
    assert pairs[(2, 3)].count == 1
    assert pairs[(2, 3)].close is True  # ihinka ↔ ihinza dans asr_confusions


def test_rejection_is_not_a_close_pair() -> None:
    entries = [_entry("d.wav", 7)]
    hyp = {"d.wav": _hyp("blabla")}
    result = evaluate(entries, replay_source(hyp), SETTINGS, lexicon=LEXICON)
    pair = result.confusion_pairs[0]
    assert pair.expected_number == 7
    assert pair.predicted_number is None
    assert pair.close is False


# --------------------------------------------------------------------------- #
# Task 5 — rapport versionné & reproductibilité
# --------------------------------------------------------------------------- #


def test_report_is_reproducible(tmp_path: Path) -> None:
    entries, hyp = _mini_corpus()
    manifest = tmp_path / "benchmark.jsonl"
    write_manifest(manifest, entries)

    def make_report() -> str:
        result = evaluate(entries, replay_source(hyp), SETTINGS, lexicon=LEXICON)
        report = build_report(
            result,
            manifest_path=manifest,
            settings=SETTINGS,
            asr_mode="replay",
            latency_source="replay",
            split="test",
            lexicon=LEXICON,
            timestamp="2026-07-24T00:00:00Z",
        )
        return report_to_json(report)

    assert make_report() == make_report()


def test_report_contains_reproducibility_metadata_and_no_pii(tmp_path: Path) -> None:
    entries, hyp = _mini_corpus()
    manifest = tmp_path / "benchmark.jsonl"
    write_manifest(manifest, entries)
    result = evaluate(entries, replay_source(hyp), SETTINGS, lexicon=LEXICON)
    report = build_report(
        result,
        manifest_path=manifest,
        settings=SETTINGS,
        asr_mode="replay",
        latency_source="replay",
        split="test",
        lexicon=LEXICON,
        timestamp="2026-07-24T00:00:00Z",
    )
    assert report["versions"]["grammar_version"] == LEXICON.grammar_version
    assert report["manifest"]["sha256"]  # empreinte présente
    assert report["settings"]["policy_thresholds"]["accept"] == SETTINGS.POLICY_ACCEPT_THRESHOLD
    # Sans PII : aucun speaker_key ni audio_path dans le rapport machine.
    blob = json.dumps(report, ensure_ascii=False)
    assert "speaker_key" not in blob
    assert "a.wav" not in blob


def test_write_report_emits_json_and_md(tmp_path: Path) -> None:
    entries, hyp = _mini_corpus()
    manifest = tmp_path / "benchmark.jsonl"
    write_manifest(manifest, entries)
    result = evaluate(entries, replay_source(hyp), SETTINGS, lexicon=LEXICON)
    report = build_report(
        result,
        manifest_path=manifest,
        settings=SETTINGS,
        asr_mode="replay",
        latency_source="replay",
        split="test",
        lexicon=LEXICON,
        timestamp="2026-07-24T00:00:00Z",
    )
    json_path, md_path = write_report(tmp_path / "out" / "benchmark", report)
    assert json_path.exists() and md_path.exists()
    assert "Exact Number Accuracy" in md_path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Rejeu I/O
# --------------------------------------------------------------------------- #


def test_hypotheses_roundtrip(tmp_path: Path) -> None:
    from evaluation import asr_result_to_dict

    path = tmp_path / "hyp.jsonl"
    rows = [asr_result_to_dict("a.wav", _asr(zarma_numbers.generate(5)))]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    loaded = load_hypotheses(path)
    assert loaded["a.wav"].text == zarma_numbers.generate(5)
