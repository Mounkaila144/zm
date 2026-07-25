"""Tests de la comparaison glouton vs contraint (story 5.6, task 5).

Le script ne recalcule **aucune** métrique : il appelle le harnais 5.2 puis met
les deux rapports côte à côte. Ces tests vérifient le protocole (split de
décision, ventilations, écart NFR2 documenté) sur des hypothèses synthétiques —
sans GPU ni réseau.
"""

from __future__ import annotations

import json

import zarma_numbers
from benchmark_corpus import ManifestEntry, speaker_key_for, write_manifest
from compare_decoding import (
    NFR2_TARGETS,
    PROTOTYPE_REFERENCE,
    build_comparison,
    comparison_to_markdown,
    main,
)


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


def _hypothesis_row(audio_path: str, text: str, score: float = 0.9) -> dict:
    return {
        "audio_path": audio_path,
        "text": text,
        "acoustic_score": score,
        "candidates": [],
        "latency_ms": 40,
        "model_version": "omniASR_CTC_300M_v2",
    }


def _write_jsonl(path, rows):
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8"
    )
    return path


def _corpus(tmp_path):
    """Manifest + hypothèses : le glouton échoue partout, le contraint réussit."""
    numbers = [(f"a{i}.wav", n) for i, n in enumerate([0, 5, 42, 100, 372, 1234])]
    entries = [
        _entry(path, n, condition="calme" if index % 2 == 0 else "bruit")
        for index, (path, n) in enumerate(numbers)
    ]
    manifest = tmp_path / "manifest.jsonl"
    write_manifest(manifest, entries)

    # Glouton : sorties non latines (le mode d'échec réellement observé).
    greedy = _write_jsonl(
        tmp_path / "greedy.jsonl",
        [_hypothesis_row(path, "你经刚", score=1.0) for path, _ in numbers],
    )
    # Contraint : formes canoniques correctes, sauf une (pour éviter un 100 % irréaliste).
    constrained_rows = []
    for index, (path, number) in enumerate(numbers):
        text = zarma_numbers.generate(number if index != 1 else number + 1)
        constrained_rows.append(_hypothesis_row(path, text))
    constrained = _write_jsonl(tmp_path / "constrained.jsonl", constrained_rows)
    return manifest, greedy, constrained


# --- CLI de bout en bout ---


def test_cli_produces_both_reports(tmp_path, capsys):
    manifest, greedy, constrained = _corpus(tmp_path)
    out = tmp_path / "comparison"
    code = main(
        [
            "--manifest",
            str(manifest),
            "--greedy",
            str(greedy),
            "--constrained",
            str(constrained),
            "--split",
            "test",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    report = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert report["overall"]["greedy"] == 0.0
    assert report["overall"]["constrained"] > 0.5
    assert report["overall"]["delta"] > 0.5
    assert "glouton" in capsys.readouterr().out


def test_cli_fails_closed_on_missing_manifest(tmp_path):
    _, greedy, constrained = _corpus(tmp_path)
    assert (
        main(
            [
                "--manifest",
                str(tmp_path / "absent.jsonl"),
                "--greedy",
                str(greedy),
                "--constrained",
                str(constrained),
                "--out",
                str(tmp_path / "cmp"),
            ]
        )
        == 2
    )


def test_cli_fails_closed_on_empty_split(tmp_path):
    manifest, greedy, constrained = _corpus(tmp_path)
    assert (
        main(
            [
                "--manifest",
                str(manifest),
                "--greedy",
                str(greedy),
                "--constrained",
                str(constrained),
                "--split",
                "dev",
                "--out",
                str(tmp_path / "cmp"),
            ]
        )
        == 2
    )


def test_cli_fails_closed_on_missing_hypotheses(tmp_path):
    manifest, greedy, _ = _corpus(tmp_path)
    assert (
        main(
            [
                "--manifest",
                str(manifest),
                "--greedy",
                str(greedy),
                "--constrained",
                str(tmp_path / "absent.jsonl"),
                "--out",
                str(tmp_path / "cmp"),
            ]
        )
        == 2
    )


# --- Contenu du rapport ---


def _fake_report(accuracy: float, *, calme: float, bruit: float) -> dict:
    def group(value: float, total: int = 10) -> dict:
        return {"accuracy": value, "correct": int(round(value * total)), "total": total}

    return {
        "harness_version": "5.2.0",
        "manifest": {"name": "m.jsonl", "sha256": "a" * 64, "entries": 20},
        "versions": {"grammar_version": "1.1.0"},
        "asr": {"model_versions": ["omniASR_CTC_300M_v2"], "mode": "replay"},
        "metrics": {
            "exact_number_accuracy": accuracy,
            "correct": int(accuracy * 20),
            "total": 20,
            "by_condition": {"calme": group(calme), "bruit": group(bruit)},
            "by_tag": {"short": group(accuracy), "long": group(accuracy)},
            "by_split": {"test": group(accuracy, 20)},
            "decision_rates": {
                "rejection_rate": 0.1,
                "false_acceptance_rate": 0.05,
                "confirmation_rate": 0.2,
                "correct_acceptance_rate": 0.65,
            },
            "asr_latency_ms": {"p50_ms": 40, "p95_ms": 90, "avg_ms": 50},
        },
    }


def test_comparison_breaks_down_by_condition_tag_and_split():
    greedy = _fake_report(0.02, calme=0.02, bruit=0.0)
    constrained = _fake_report(0.80, calme=0.9, bruit=0.7)
    comparison = build_comparison(greedy, constrained, split="test")

    assert comparison["overall"]["delta"] == 0.78
    assert set(comparison["breakdown"]) == {"by_condition", "by_tag", "by_split"}
    assert comparison["breakdown"]["by_condition"]["calme"]["delta"] == 0.88
    assert comparison["breakdown"]["by_condition"]["bruit"]["delta"] == 0.70
    assert comparison["breakdown"]["by_split"]["test"]["constrained"] == 0.80


def test_comparison_documents_the_gap_to_nfr2_without_hiding_it():
    constrained = _fake_report(0.80, calme=0.9, bruit=0.7)
    comparison = build_comparison(
        _fake_report(0.02, calme=0.02, bruit=0.0), constrained, split="test"
    )

    gaps = {gap["condition"]: gap for gap in comparison["nfr2"]["constrained_gap"]}
    assert gaps["calme"]["target"] == NFR2_TARGETS["calme"]
    # 0.90 mesuré contre 0.95 visé → écart négatif explicite, objectif non atteint.
    assert gaps["calme"]["gap"] == -0.05
    assert gaps["calme"]["meets_target"] is False
    assert gaps["bruit"]["gap"] == -0.20
    assert gaps["bruit"]["meets_target"] is False

    markdown = comparison_to_markdown(comparison)
    assert "Écart aux objectifs NFR2" in markdown
    assert "❌" in markdown


def test_comparison_marks_targets_that_are_met():
    constrained = _fake_report(0.96, calme=0.97, bruit=0.92)
    comparison = build_comparison(
        _fake_report(0.02, calme=0.0, bruit=0.0), constrained, split="test"
    )
    gaps = {gap["condition"]: gap for gap in comparison["nfr2"]["constrained_gap"]}
    assert gaps["calme"]["meets_target"] is True
    assert gaps["bruit"]["meets_target"] is True
    assert "✅" in comparison_to_markdown(comparison)


def test_comparison_recalls_the_prototype_reference():
    comparison = build_comparison(
        _fake_report(0.02, calme=0.02, bruit=0.0),
        _fake_report(0.80, calme=0.9, bruit=0.7),
        split="test",
    )
    reference = comparison["prototype_reference"]
    assert reference["constrained_accuracy"] == PROTOTYPE_REFERENCE["constrained_accuracy"]
    assert reference["constrained_accuracy_unseen_speaker"] == 0.79
    markdown = comparison_to_markdown(comparison)
    assert "référence du prototype" in markdown


def test_comparison_carries_reproducibility_metadata():
    comparison = build_comparison(
        _fake_report(0.02, calme=0.0, bruit=0.0),
        _fake_report(0.80, calme=0.9, bruit=0.7),
        split="test",
    )
    assert comparison["grammar_version"] == "1.1.0"
    assert comparison["harness_version"] == "5.2.0"
    assert comparison["split_evaluated"] == "test"
    assert comparison["decision_rates"]["constrained"]["rejection_rate"] == 0.1
