"""Validation, décodage et normalisation sécurisés des uploads audio WAV."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

import numpy as np
import soundfile as sf
import soxr
from fastapi import UploadFile, status

MAX_AUDIO_SIZE = 2_000_000
ALLOWED_MIME_TYPES = frozenset({"audio/wav", "audio/x-wav"})

TARGET_SAMPLE_RATE = 16_000
TARGET_CHANNELS = 1
TARGET_SAMPLE_WIDTH = 2
WAV_MAGIC = b"RIFF"
WAV_FORMAT = b"WAVE"


@dataclass(frozen=True, slots=True)
class DecodedAudio:
    """Audio brut normalisé, prêt à être transmis au recognizer."""

    pcm: bytes
    sample_rate: int
    channels: int
    sample_width: int
    duration_ms: int


class AudioValidationError(Exception):
    """Erreur audio contrôlée, traduite par la route en réponse API sûre."""

    def __init__(self, *, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _invalid_audio(message: str) -> AudioValidationError:
    return AudioValidationError(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="AUDIO_INVALID",
        message=message,
    )


def _has_wav_magic(content: bytes) -> bool:
    """Vérifie la signature RIFF/WAVE sans se fier au nom ou au MIME déclaré."""

    return len(content) >= 12 and content[:4] == WAV_MAGIC and content[8:12] == WAV_FORMAT


def _decode_wav(content: bytes) -> tuple[np.ndarray, int]:
    """Décode un WAV en mémoire dans un tableau float32 (frames, canaux)."""

    try:
        data, sample_rate = sf.read(
            BytesIO(content),
            dtype="float32",
            always_2d=True,
        )
    except (OSError, RuntimeError, TypeError, ValueError, sf.LibsndfileError) as exc:
        raise _invalid_audio("Corrupted audio file") from exc

    if data.size == 0 or data.shape[0] == 0:
        raise _invalid_audio("Audio file contains no audio data")
    if data.shape[1] == 0 or sample_rate <= 0 or not np.isfinite(data).all():
        raise _invalid_audio("Corrupted audio file")
    return data, sample_rate


def _normalize_pcm16(data: np.ndarray, sample_rate: int) -> bytes:
    """Down-mixe, ré-échantillonne et quantifie en PCM16 mono 16 kHz."""

    try:
        mono = data[:, 0] if data.shape[1] == 1 else data.mean(axis=1)
        if sample_rate != TARGET_SAMPLE_RATE:
            mono = soxr.resample(
                mono,
                sample_rate,
                TARGET_SAMPLE_RATE,
            )
        if mono.size == 0 or not np.isfinite(mono).all():
            raise ValueError("empty or non-finite normalized audio")
        pcm16 = np.rint(mono * 32_768.0).clip(-32_768, 32_767).astype("<i2")
    except (OverflowError, TypeError, ValueError) as exc:
        raise _invalid_audio("Corrupted audio file") from exc

    return pcm16.tobytes()


async def validate_and_decode(audio: UploadFile) -> DecodedAudio:
    """Valide un upload WAV puis produit du PCM16 mono 16 kHz en mémoire."""

    if audio.content_type not in ALLOWED_MIME_TYPES:
        raise _invalid_audio("Invalid audio format")

    content = await audio.read(MAX_AUDIO_SIZE + 1)
    if len(content) > MAX_AUDIO_SIZE:
        raise AudioValidationError(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            code="FILE_TOO_LARGE",
            message=f"File too large (max {MAX_AUDIO_SIZE // 1_000_000}MB)",
        )
    if not content:
        raise _invalid_audio("Audio file cannot be empty")
    if not _has_wav_magic(content):
        raise _invalid_audio("Invalid or inconsistent audio content")
    riff_size = int.from_bytes(content[4:8], "little")
    if riff_size > len(content) - 8:
        raise _invalid_audio("Corrupted audio file")

    data, sample_rate = _decode_wav(content)
    pcm = _normalize_pcm16(data, sample_rate)
    duration_ms = round(
        len(pcm) / (TARGET_SAMPLE_RATE * TARGET_CHANNELS * TARGET_SAMPLE_WIDTH) * 1000
    )

    return DecodedAudio(
        pcm=pcm,
        sample_rate=TARGET_SAMPLE_RATE,
        channels=TARGET_CHANNELS,
        sample_width=TARGET_SAMPLE_WIDTH,
        duration_ms=duration_ms,
    )
