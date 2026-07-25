"""Tests de la configuration du service ASR (story 5.6, task 7).

Exigence de standard : **aucun paramètre de décodage en dur** — tout passe par
``AsrSettings`` et se retrouve dans le ``DecoderConfig`` effectif.
"""

from __future__ import annotations

import pytest


def test_defaults_match_the_validated_values(asr_config):
    settings = asr_config.AsrSettings()
    # Annexe A §3 : p = 1.0 est l'optimum mesuré.
    assert settings.DECODE_LENGTH_EXPONENT == 1.0
    # Annexe D §1 : blank = 0, surtout PAS 1 malgré pad_idx=1.
    assert settings.DECODE_BLANK_ID == 0
    assert settings.DECODE_CONSTRAINED is True
    # Un seuil non calibré serait pire que pas de rejet du tout.
    assert settings.DECODE_REJECT_THRESHOLD == 0.0


def test_settings_map_onto_the_decoder_config(asr_config):
    settings = asr_config.AsrSettings(
        DECODE_BEAM_WIDTH=128,
        DECODE_NBEST=3,
        DECODE_BLANK_ID=0,
        DECODE_LENGTH_EXPONENT=1.2,
        DECODE_MIN_FRAMES_PER_TOKEN=2.0,
        DECODE_EXACT_RESCORE=False,
        DECODE_REJECT_THRESHOLD=0.4,
    )
    config = settings.decoder_config()
    assert config.beam_width == 128
    assert config.nbest == 3
    assert config.length_exponent == 1.2
    assert config.min_frames_per_token == 2.0
    assert config.exact_rescore is False
    assert config.reject_threshold == 0.4


def test_settings_are_read_from_the_environment(asr_config, monkeypatch):
    monkeypatch.setenv("DECODE_BEAM_WIDTH", "16")
    monkeypatch.setenv("DECODE_REJECT_THRESHOLD", "0.25")
    settings = asr_config.AsrSettings()
    assert settings.DECODE_BEAM_WIDTH == 16
    assert settings.decoder_config().reject_threshold == 0.25


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("", ()), ("5262", (5262,)), ("1, 2 3", (1, 2, 3)), ("  ", ())],
)
def test_separator_ids_parsing(asr_config, raw, expected):
    assert asr_config.AsrSettings(DECODE_SEPARATOR_IDS=raw).separator_ids() == expected


@pytest.mark.parametrize(
    "invalid",
    [
        {"DECODE_BEAM_WIDTH": 0},
        {"DECODE_NBEST": 0},
        {"DECODE_REJECT_THRESHOLD": 1.5},
        {"DECODE_REJECT_THRESHOLD": -0.1},
        {"DECODE_LENGTH_EXPONENT": -1.0},
    ],
)
def test_invalid_values_are_refused(asr_config, invalid):
    with pytest.raises(ValueError):
        asr_config.AsrSettings(**invalid)


def test_disabling_constraint_is_explicit(asr_config, monkeypatch):
    monkeypatch.setenv("DECODE_CONSTRAINED", "false")
    assert asr_config.AsrSettings().DECODE_CONSTRAINED is False
