"""Tests de la calibration du seuil de rejet (story 5.6, task 3).

Le protocole doit être **fail-closed sur le split de test** (NFR10) et refuser
de proposer un seuil quand aucun ne tient la contrainte — plutôt que d'afficher
un chiffre flatteur.
"""

from __future__ import annotations

import json

import pytest
from calibrate_rejection import (
    CalibrationError,
    build_report,
    load_observations,
    main,
    report_to_markdown,
    select_threshold,
    sweep,
)


def _write(path, rows):
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    return path


def _observation(name, *, confidence, is_numeric=True, split="dev"):
    return {
        "audio_path": name,
        "split": split,
        "is_numeric": is_numeric,
        "confidence": confidence,
    }


# --- Fail-closed : jamais de calibration sur le split de test (NFR10) ---


def test_test_split_is_refused(tmp_path):
    path = _write(
        tmp_path / "obs.jsonl",
        [
            _observation("a.wav", confidence=0.9),
            _observation("b.wav", confidence=0.2, split="test"),
        ],
    )
    with pytest.raises(CalibrationError, match="test"):
        load_observations(path)


def test_dev_split_is_accepted(tmp_path):
    path = _write(tmp_path / "obs.jsonl", [_observation("a.wav", confidence=0.9)])
    observations = load_observations(path)
    assert len(observations) == 1
    assert observations[0].split == "dev"


def test_split_filter_restricts_further(tmp_path):
    path = _write(
        tmp_path / "obs.jsonl",
        [
            _observation("a.wav", confidence=0.9, split="dev"),
            _observation("b.wav", confidence=0.5, split="calibration"),
        ],
    )
    assert len(load_observations(path, split="dev")) == 1
    assert len(load_observations(path, split="all")) == 2


def test_invalid_line_is_refused(tmp_path):
    path = tmp_path / "obs.jsonl"
    path.write_text('{"audio_path": "a.wav"}\n', encoding="utf-8")
    with pytest.raises(CalibrationError):
        load_observations(path)


def test_missing_file_is_refused(tmp_path):
    with pytest.raises(CalibrationError):
        load_observations(tmp_path / "absent.jsonl")


def test_empty_after_filtering_is_refused(tmp_path):
    path = _write(tmp_path / "obs.jsonl", [_observation("a.wav", confidence=0.9, split="dev")])
    with pytest.raises(CalibrationError):
        load_observations(path, split="calibration")


# --- Balayage et sélection ---


def _mixed_observations():
    numeric = [
        _observation(f"n{i}.wav", confidence=c) for i, c in enumerate([0.95, 0.9, 0.85, 0.8])
    ]
    non_numeric = [
        _observation(f"x{i}.wav", confidence=c, is_numeric=False)
        for i, c in enumerate([0.05, 0.1, 0.2, 0.6])
    ]
    return numeric + non_numeric


def test_sweep_covers_every_observed_confidence(tmp_path):
    path = _write(tmp_path / "obs.jsonl", _mixed_observations())
    points = sweep(load_observations(path))
    thresholds = {point.threshold for point in points}
    assert 0.0 in thresholds
    assert {0.05, 0.1, 0.2, 0.6, 0.8, 0.85, 0.9, 0.95} <= thresholds


def test_zero_threshold_accepts_everything(tmp_path):
    path = _write(tmp_path / "obs.jsonl", _mixed_observations())
    points = sweep(load_observations(path))
    zero = next(point for point in points if point.threshold == 0.0)
    assert zero.recall == 1.0
    assert zero.false_acceptance_rate == 1.0


def test_selection_separates_numeric_from_non_numeric(tmp_path):
    path = _write(tmp_path / "obs.jsonl", _mixed_observations())
    points = sweep(load_observations(path))
    selected = select_threshold(points, max_false_acceptance=0.0)
    assert selected is not None
    # Le seul seuil sans fausse acceptation est > 0.6 et garde tous les nombres.
    assert selected.threshold > 0.6
    assert selected.recall == 1.0
    assert selected.false_acceptance_rate == 0.0


def test_selection_returns_none_when_no_threshold_qualifies():
    # Non-numériques tous plus confiants que les nombres : aucun seuil ne sépare.
    observations = sweep(
        [
            type(
                "O", (), {"is_numeric": True, "confidence": 0.1, "split": "dev", "audio_path": "a"}
            )(),
            type(
                "O", (), {"is_numeric": False, "confidence": 0.9, "split": "dev", "audio_path": "b"}
            )(),
        ]
    )
    assert select_threshold(observations, max_false_acceptance=0.0) is None


def test_selection_respects_the_tolerance(tmp_path):
    path = _write(tmp_path / "obs.jsonl", _mixed_observations())
    points = sweep(load_observations(path))
    tolerant = select_threshold(points, max_false_acceptance=0.25)
    strict = select_threshold(points, max_false_acceptance=0.0)
    assert tolerant is not None and strict is not None
    # Plus la tolérance est grande, plus le seuil peut être bas (rappel préservé).
    assert tolerant.threshold <= strict.threshold


# --- Rapport ---


def test_report_documents_the_protocol(tmp_path):
    path = _write(tmp_path / "obs.jsonl", _mixed_observations())
    observations = load_observations(path)
    points = sweep(observations)
    selected = select_threshold(points, max_false_acceptance=0.0)
    report = build_report(
        points,
        selected,
        observations=observations,
        source=path,
        max_false_acceptance=0.0,
        split="dev",
    )
    assert report["protocol"]["forbidden_split"] == "test"
    assert report["protocol"]["split_used"] == "dev"
    assert report["selected"]["setting"] == "DECODE_REJECT_THRESHOLD"
    assert report["observations"]["numeric"] == 4
    assert report["observations"]["non_numeric"] == 4
    assert len(report["curve"]) == len(points)
    markdown = report_to_markdown(report)
    assert "Seuil retenu" in markdown
    assert "NFR10" in markdown


def test_markdown_says_so_when_no_threshold_is_retained(tmp_path):
    path = _write(tmp_path / "obs.jsonl", _mixed_observations())
    observations = load_observations(path)
    report = build_report(
        sweep(observations),
        None,
        observations=observations,
        source=path,
        max_false_acceptance=0.0,
        split="dev",
    )
    markdown = report_to_markdown(report)
    assert "Aucun seuil retenu" in markdown
    assert "0.0" in markdown


# --- CLI ---


def test_cli_writes_reports_and_reports_the_threshold(tmp_path, capsys):
    path = _write(tmp_path / "obs.jsonl", _mixed_observations())
    out = tmp_path / "calib"
    code = main(
        [
            "--observations",
            str(path),
            "--max-false-acceptance",
            "0.0",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    assert out.with_suffix(".json").is_file()
    assert out.with_suffix(".md").is_file()
    assert "DECODE_REJECT_THRESHOLD=" in capsys.readouterr().out


def test_cli_fails_closed_on_test_split(tmp_path):
    path = _write(tmp_path / "obs.jsonl", [_observation("a.wav", confidence=0.5, split="test")])
    assert main(["--observations", str(path), "--out", str(tmp_path / "calib")]) == 2
