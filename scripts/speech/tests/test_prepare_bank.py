"""Préparation d'une séance d'enregistrement (story 6.1, task 6).

Le locuteur enregistre avec son matériel ; le format canonique du projet est
rarement celui qui sort du micro. Ce qui est prouvé ici :

- la conversion produit **exactement** le format que la banque sait lire ;
- les silences promis au locuteur (« laisse 0,5 s, je couperai ») sont bien
  coupés — sinon chaque mot traîne une pause et l'assemblage sonne haché ;
- un nom de fichier n'est corrigé que sur une faute **mécanique** vérifiable ;
  jamais par rapprochement approximatif.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from prepare_bank import (
    canonical_name,
    load_mono,
    prepare,
    to_canonical_pcm,
    trim_silence,
)
from voice_bank import TARGET_RATE, build_bank, number_coverage, target_vocabulary

VOCABULARY = target_vocabulary()


def write_source(path: Path, samples: np.ndarray, rate: int = 44_100) -> None:
    """Écrit un WAV « tel que sorti du micro » (44,1 kHz par défaut)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), samples.astype("float32"), rate, subtype="PCM_16")


def tone(seconds: float, rate: int = 44_100, amplitude: float = 0.5) -> np.ndarray:
    t = np.linspace(0.0, seconds, int(seconds * rate), endpoint=False)
    return amplitude * np.sin(2 * np.pi * 220.0 * t)


def padded_tone(silence: float, speech: float, rate: int = 44_100) -> np.ndarray:
    quiet = np.zeros(int(silence * rate), dtype="float32")
    return np.concatenate([quiet, tone(speech, rate), quiet])


# --------------------------------------------------------------------------- #
# Conversion
# --------------------------------------------------------------------------- #


def test_conversion_produces_the_canonical_format(tmp_path):
    source = tmp_path / "raw" / "waranka.wav"
    write_source(source, tone(0.5))

    prepare(source.parent, tmp_path / "out")

    with wave.open(str(tmp_path / "out" / "words" / "waranka.wav"), "rb") as reader:
        assert reader.getnchannels() == 1
        assert reader.getframerate() == TARGET_RATE
        assert reader.getsampwidth() == 2


def test_conversion_preserves_duration(tmp_path):
    samples, rate = tone(0.5), 44_100
    pcm = to_canonical_pcm(samples, rate)
    duration = len(pcm) / (TARGET_RATE * 2)
    assert duration == pytest.approx(0.5, abs=0.01)


def test_a_stereo_source_becomes_mono(tmp_path):
    source = tmp_path / "raw" / "waranka.wav"
    source.parent.mkdir(parents=True)
    mono = tone(0.3)
    sf.write(str(source), np.stack([mono, mono], axis=1), 44_100, subtype="PCM_16")

    samples, rate = load_mono(source)
    assert samples.ndim == 1
    assert rate == 44_100


def test_an_already_canonical_file_is_left_at_16k(tmp_path):
    source = tmp_path / "raw" / "waranka.wav"
    write_source(source, tone(0.4, rate=TARGET_RATE), rate=TARGET_RATE)

    prepare(source.parent, tmp_path / "out")

    with wave.open(str(tmp_path / "out" / "words" / "waranka.wav"), "rb") as reader:
        assert reader.getframerate() == TARGET_RATE


# --------------------------------------------------------------------------- #
# Détourage des silences
# --------------------------------------------------------------------------- #


def test_leading_and_trailing_silence_are_removed():
    rate = 44_100
    trimmed = trim_silence(padded_tone(0.5, 0.4, rate), rate)
    duration = trimmed.size / rate
    assert 0.4 <= duration < 0.55  # le mot, plus la petite marge


def test_trimming_keeps_a_margin_around_the_word():
    rate = 44_100
    trimmed = trim_silence(padded_tone(0.5, 0.4, rate), rate)
    assert trimmed.size / rate > 0.4


def test_a_fully_silent_file_is_not_reduced_to_nothing():
    """Un fichier muet doit rester visiblement muet, pas disparaître."""
    silence = np.zeros(4_410, dtype="float32")
    assert trim_silence(silence, 44_100).size == silence.size


def test_trimming_can_be_disabled(tmp_path):
    source = tmp_path / "raw" / "waranka.wav"
    write_source(source, padded_tone(0.5, 0.2))

    prepare(source.parent, tmp_path / "kept", trim=False)
    prepare(source.parent, tmp_path / "cut", trim=True)

    def duration(root: Path) -> float:
        with wave.open(str(root / "words" / "waranka.wav"), "rb") as reader:
            return reader.getnframes() / reader.getframerate()

    assert duration(tmp_path / "kept") > duration(tmp_path / "cut")


# --------------------------------------------------------------------------- #
# Noms de fichier : corriger une faute mécanique, jamais deviner
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("stem", "expected"),
    [("igouwav", "igou"), ("taciwav", "taci"), ("waytaciwav", "waytaci")],
)
def test_the_doubled_extension_typo_is_repaired(stem, expected):
    assert canonical_name(stem, VOCABULARY) == (expected, True)


def test_a_correct_name_is_untouched():
    assert canonical_name("waranka", VOCABULARY) == ("waranka", False)


def test_a_declared_variant_is_resolved_to_its_canonical_form():
    """`zongou` → `zangou` : ce n'est pas une devinette, c'est la table du lexique."""
    assert canonical_name("zongou", VOCABULARY) == ("zangou", True)


def test_an_unknown_name_is_never_guessed():
    """Aucun rapprochement approximatif : un nom hors lexique reste tel quel."""
    assert canonical_name("waranke", VOCABULARY) == ("waranke", False)
    assert canonical_name("zangu", VOCABULARY) == ("zangu", False)


def test_unknown_files_are_reported_not_dropped_silently(tmp_path):
    source = tmp_path / "raw"
    write_source(source / "waranka.wav", tone(0.3))
    write_source(source / "bruit ambiant1.wav", tone(0.3))

    report = prepare(source, tmp_path / "out")
    assert report.unknown == ["bruit ambiant1.wav"]
    assert "waranka" in report.words


# --------------------------------------------------------------------------- #
# Tri et bilan
# --------------------------------------------------------------------------- #


def test_prompts_are_separated_from_words(tmp_path):
    source = tmp_path / "raw"
    write_source(source / "waranka.wav", tone(0.3))
    write_source(source / "confirm.wav", tone(1.0))

    report = prepare(source, tmp_path / "out")
    assert set(report.words) == {"waranka"}
    assert set(report.prompts) == {"confirm"}
    assert (tmp_path / "out" / "prompts" / "confirm.wav").is_file()


def test_report_lists_what_is_still_missing(tmp_path):
    source = tmp_path / "raw"
    write_source(source / "waranka.wav", tone(0.3))

    report = prepare(source, tmp_path / "out")
    assert not report.ok
    assert "waranka" not in report.missing_words
    assert "cindi" in report.missing_words
    assert report.missing_prompts == ["confirm", "cannot_answer"]


def test_dry_run_writes_nothing(tmp_path):
    source = tmp_path / "raw"
    write_source(source / "waranka.wav", tone(0.3))
    out = tmp_path / "out"

    report = prepare(source, None, dry_run=True)
    assert "waranka" in report.words
    assert not out.exists()


def test_an_unreadable_file_is_reported_not_swallowed(tmp_path):
    source = tmp_path / "raw"
    source.mkdir()
    (source / "waranka.wav").write_bytes(b"pas du tout un wav")

    report = prepare(source, tmp_path / "out")
    assert [name for name, _ in report.failed] == ["waranka.wav"]
    assert not report.ok


def test_a_complete_session_yields_a_usable_bank(tmp_path):
    """De bout en bout : prises brutes 44,1 kHz → banque qui dit tous les nombres."""
    source = tmp_path / "raw"
    for word in VOCABULARY:
        write_source(source / f"{word}.wav", padded_tone(0.3, 0.25))
    for prompt in ("confirm", "cannot_answer"):
        write_source(source / f"{prompt}.wav", tone(1.5))

    report = prepare(source, tmp_path / "out")
    assert report.ok

    bank = build_bank(
        "v4",
        sources=(),
        word_dir=tmp_path / "out" / "words",
        prompt_dir=tmp_path / "out" / "prompts",
    )
    assert number_coverage(bank) == (1001, 1001)
