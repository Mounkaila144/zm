"""Tests de sécurité et de normalisation du pipeline audio (story 2.4)."""

from __future__ import annotations

import math
import struct
import wave
from io import BytesIO
from uuid import UUID

import pytest
import zarma_numbers
from app.asr.base import AsrResult, AudioInput
from app.asr.factory import get_recognizer
from app.main import app
from app.pipeline import audio as audio_pipeline
from app.pipeline.audio import (
    MAX_AUDIO_SIZE,
    TARGET_CHANNELS,
    TARGET_SAMPLE_RATE,
    TARGET_SAMPLE_WIDTH,
)
from fastapi.testclient import TestClient

client = TestClient(app)
ANON_ID = "00000000-0000-4000-8000-000000000024"


def make_wav(
    *,
    channels: int = 1,
    sample_rate: int = 16_000,
    duration_ms: int = 100,
) -> bytes:
    """Construit en mémoire un signal WAV PCM16 valide."""

    frame_count = sample_rate * duration_ms // 1000
    frames = bytearray()
    for frame_index in range(frame_count):
        sample = int(10_000 * math.sin(2 * math.pi * 440 * frame_index / sample_rate))
        for channel_index in range(channels):
            channel_sample = sample if channel_index == 0 else sample // 2
            frames.extend(struct.pack("<h", channel_sample))

    output = BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(TARGET_SAMPLE_WIDTH)
        target.setframerate(sample_rate)
        target.writeframes(frames)
    return output.getvalue()


def post_audio(audio: bytes, mime_type: str = "audio/wav") -> object:
    return client.post(
        "/api/v1/recognize",
        files={"audio": ("security.wav", audio, mime_type)},
        data={"anon_id": ANON_ID},
    )


class SpyRecognizer:
    def __init__(self) -> None:
        self.received: AudioInput | None = None

    @property
    def model_version(self) -> str:
        return "spy-1.0.0"

    def transcribe(self, audio: AudioInput) -> AsrResult:
        self.received = audio
        return AsrResult(
            text=zarma_numbers.generate(42),
            acoustic_score=1.0,
            candidates=[],
            latency_ms=1,
            model_version=self.model_version,
        )


@pytest.fixture
def spy_recognizer() -> SpyRecognizer:
    recognizer = SpyRecognizer()
    app.dependency_overrides[get_recognizer] = lambda: recognizer
    try:
        yield recognizer
    finally:
        app.dependency_overrides.pop(get_recognizer, None)


def assert_safe_audio_error(response: object, expected_status: int) -> dict[str, object]:
    assert response.status_code == expected_status
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "AUDIO_INVALID"
    assert UUID(body["error"]["request_id"])
    serialized = response.text.lower()
    assert "traceback" not in serialized
    assert "wave.error" not in serialized
    return body


def test_valid_wav_is_normalized_before_asr(spy_recognizer: SpyRecognizer) -> None:
    response = post_audio(make_wav(channels=2, sample_rate=44_100))

    assert response.status_code == 200
    assert response.json()["recognized_number"] == 42
    assert spy_recognizer.received is not None
    assert spy_recognizer.received.format == "pcm_s16le"
    assert len(spy_recognizer.received.data) == (
        TARGET_SAMPLE_RATE * TARGET_CHANNELS * TARGET_SAMPLE_WIDTH // 10
    )


def test_corrupted_wav_is_rejected(spy_recognizer: SpyRecognizer) -> None:
    corrupted = b"RIFF" + (100).to_bytes(4, "little") + b"WAVEfmt "

    response = post_audio(corrupted)

    body = assert_safe_audio_error(response, 422)
    assert body["error"]["message"] == "Corrupted audio file"
    assert spy_recognizer.received is None


def test_truncated_wav_is_rejected(spy_recognizer: SpyRecognizer) -> None:
    valid = make_wav()

    response = post_audio(valid[:-17])

    assert_safe_audio_error(response, 422)
    assert spy_recognizer.received is None


def test_oversized_file_is_rejected_before_decoding(
    monkeypatch: pytest.MonkeyPatch,
    spy_recognizer: SpyRecognizer,
) -> None:
    def decoding_must_not_run(*args: object, **kwargs: object) -> object:
        raise AssertionError("decoder called for oversized input")

    monkeypatch.setattr(audio_pipeline.sf, "read", decoding_must_not_run)

    response = post_audio(b"R" * (MAX_AUDIO_SIZE + 1))

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert "too large" in response.json()["error"]["message"].lower()
    assert spy_recognizer.received is None


@pytest.mark.parametrize("payload", [b"\x89PNG\r\n\x1a\n", b"plain text"])
def test_declared_wav_with_inconsistent_content_is_rejected(
    payload: bytes,
    spy_recognizer: SpyRecognizer,
) -> None:
    response = post_audio(payload, "audio/wav")

    body = assert_safe_audio_error(response, 422)
    assert body["error"]["message"] == "Invalid or inconsistent audio content"
    assert spy_recognizer.received is None


def test_declared_non_wav_mime_is_rejected(spy_recognizer: SpyRecognizer) -> None:
    response = post_audio(make_wav(), "image/png")

    body = assert_safe_audio_error(response, 422)
    assert body["error"]["message"] == "Invalid audio format"
    assert spy_recognizer.received is None


def test_empty_wav_data_chunk_is_rejected(spy_recognizer: SpyRecognizer) -> None:
    response = post_audio(make_wav(duration_ms=0))

    body = assert_safe_audio_error(response, 422)
    assert body["error"]["message"] == "Audio file contains no audio data"
    assert spy_recognizer.received is None


@pytest.mark.asyncio
async def test_already_normalized_pcm16_is_idempotent() -> None:
    from fastapi import UploadFile

    wav = make_wav()
    upload = UploadFile(filename="normalized.wav", file=BytesIO(wav))
    upload.headers = {"content-type": "audio/wav"}

    decoded = await audio_pipeline.validate_and_decode(upload)

    with wave.open(BytesIO(wav), "rb") as source:
        original_pcm = source.readframes(source.getnframes())
    assert decoded.pcm == original_pcm
    assert decoded.sample_rate == TARGET_SAMPLE_RATE
    assert decoded.channels == TARGET_CHANNELS
    assert decoded.sample_width == TARGET_SAMPLE_WIDTH
    assert decoded.duration_ms == 100
    await upload.close()
