"""Tests du corpus de benchmark : intégrité, non-fuite, couverture, reproductibilité."""

from __future__ import annotations

from pathlib import Path

import pytest
import zarma_numbers
from benchmark_corpus import (
    CONDITIONS,
    assign_split,
    build_manifest,
    build_recording_plan,
    read_manifest,
    select_target_numbers,
    speaker_key_for,
    validate_manifest,
    write_manifest,
)

LEXICON = zarma_numbers.load_lexicon()


def _source_from_plan(speakers: list[str]) -> list[dict]:
    """Simule un index d'audios enregistrés à partir du plan (sans audio réel)."""

    targets = select_target_numbers(LEXICON)
    plan = build_recording_plan(targets, speakers)
    rows: list[dict] = []
    for index, item in enumerate(plan):
        rows.append(
            {
                "audio_path": f"{item.speaker}_{index:04d}.wav",
                "speaker": item.speaker,
                "expected_number": item.expected_number,
                "condition": item.condition,
                "region": "Niamey",
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# Task 3 — représentativité / couverture
# --------------------------------------------------------------------------- #


def test_targets_cover_short_long_and_confusion() -> None:
    targets = select_target_numbers(LEXICON)
    tags = {tag for target in targets for tag in target.tags}
    assert {"short", "long", "confusion"} <= tags
    # Les prompts sont bien les formes canoniques du moteur (source unique).
    for target in targets:
        assert target.prompt == zarma_numbers.generate(target.value)


def test_target_selection_is_deterministic() -> None:
    first = select_target_numbers(LEXICON)
    second = select_target_numbers(LEXICON)
    assert [t.value for t in first] == [t.value for t in second]


def test_plan_reaches_100_audios_with_several_speakers() -> None:
    targets = select_target_numbers(LEXICON)
    plan = build_recording_plan(targets, ["spk01", "spk02", "spk03", "spk04"])
    assert len(plan) >= 100
    assert {item.condition for item in plan} == set(CONDITIONS)


# --------------------------------------------------------------------------- #
# Task 2 — split strict par locuteur
# --------------------------------------------------------------------------- #


def test_split_is_a_pure_function_of_speaker() -> None:
    key = speaker_key_for("spk01")
    assert assign_split(key) == assign_split(key)


def test_manifest_never_leaks_a_speaker_across_splits() -> None:
    rows = _source_from_plan(["spk01", "spk02", "spk03", "spk04", "spk05"])
    result = build_manifest(rows)
    assert result.written is True
    splits_per_speaker: dict[str, set[str]] = {}
    for entry in result.entries:
        splits_per_speaker.setdefault(entry.speaker_key, set()).add(entry.split)
    assert all(len(splits) == 1 for splits in splits_per_speaker.values())
    # Les deux splits sont représentés avec assez de locuteurs.
    assert {entry.split for entry in result.entries} == {"test", "dev"}


# --------------------------------------------------------------------------- #
# Task 4 — reproductibilité & intégrité
# --------------------------------------------------------------------------- #


def test_manifest_is_reproducible(tmp_path: Path) -> None:
    rows = _source_from_plan(["spk01", "spk02", "spk03", "spk04"])
    out_a = tmp_path / "a.jsonl"
    out_b = tmp_path / "b.jsonl"
    write_manifest(out_a, build_manifest(rows).entries)
    write_manifest(out_b, build_manifest(list(reversed(rows))).entries)
    # Même contenu quel que soit l'ordre d'entrée → reproductible.
    assert out_a.read_text() == out_b.read_text()


def test_validate_flags_speaker_leakage() -> None:
    rows = _source_from_plan(["spk01", "spk02", "spk03", "spk04"])
    entries = build_manifest(rows).entries
    # Force une fuite : réaffecte un locuteur du 'test' vers 'dev'.
    victim = next(e for e in entries if e.split == "test")
    from dataclasses import replace

    leaked = [replace(victim, split="dev")] + entries
    report = validate_manifest(leaked, min_audios=1, min_speakers=1)
    assert report.leaking_speakers == [victim.speaker_key]
    assert report.ok is False


def test_validate_passes_on_healthy_corpus(tmp_path: Path) -> None:
    rows = _source_from_plan(["spk01", "spk02", "spk03", "spk04"])
    manifest = tmp_path / "benchmark.jsonl"
    write_manifest(manifest, build_manifest(rows).entries)
    report = validate_manifest(read_manifest(manifest))
    assert report.ok is True
    assert report.total_audios >= 100
    assert report.speakers == 4
    assert {"short", "long", "confusion"} <= set(report.per_tag)


# --------------------------------------------------------------------------- #
# Fail-closed sur vérité terrain / métadonnées invalides
# --------------------------------------------------------------------------- #


def _row(**overrides: object) -> dict:
    base = {"audio_path": "x.wav", "speaker": "s", "expected_number": 5, "condition": "calme"}
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    ("bad_row", "reason"),
    [
        (_row(expected_number=2_000_000), "expected_number_invalid"),
        (_row(condition="chuchote"), "condition_invalid"),
        (_row(expected_prompt="faux"), "prompt_mismatch"),
        (_row(audio_path="sub/x.wav"), "audio_path_not_relative"),
    ],
)
def test_build_fails_closed_on_invalid_row(bad_row: dict, reason: str) -> None:
    result = build_manifest([bad_row])
    assert result.written is False
    assert any(error.reason == reason for error in result.errors)


def test_build_verifies_physical_audio_when_root_given(tmp_path: Path) -> None:
    (tmp_path / "present.wav").write_bytes(b"RIFF....WAVE")
    rows = [
        {"audio_path": "present.wav", "speaker": "s1", "expected_number": 5, "condition": "calme"},
        {"audio_path": "absent.wav", "speaker": "s2", "expected_number": 6, "condition": "bruit"},
    ]
    result = build_manifest(rows, audio_root=tmp_path, allow_partial=True)
    assert result.written is True
    assert {e.audio_path for e in result.entries} == {"present.wav"}
    assert any(e.reason == "audio_missing" for e in result.errors)
