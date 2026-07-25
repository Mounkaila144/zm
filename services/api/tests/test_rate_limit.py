"""Tests du rate limiting, des erreurs sûres et de l'anonymat de l'API."""

from __future__ import annotations

import wave
from datetime import datetime
from io import BytesIO
from uuid import UUID, uuid4

import pytest
import zarma_numbers
from app.asr.factory import get_recognizer
from app.asr.mock import MockRecognizer
from app.config import get_settings
from app.core.rate_limit import anonymous_key, limiter
from app.db.repositories import get_recognition_repo
from app.main import app, create_app
from fastapi import Request
from fastapi.testclient import TestClient

client = TestClient(app)
ANON_ID = "00000000-0000-4000-8000-000000000027"


def make_wav() -> bytes:
    """Construit un WAV PCM16 minimal et valide."""

    output = BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16_000)
        target.writeframes(b"\x00\x00" * 1_600)
    return output.getvalue()


def post_audio(anon_id: str = ANON_ID) -> object:
    return client.post(
        "/api/v1/recognize",
        files={"audio": ("rate-limit.wav", make_wav(), "audio/wav")},
        data={"anon_id": anon_id},
    )


def assert_error_envelope(response: object, code: str, status_code: int) -> dict[str, str]:
    assert response.status_code == status_code
    assert set(response.json()) == {"error"}
    error = response.json()["error"]
    assert set(error) == {"code", "message", "request_id", "timestamp"}
    assert error["code"] == code
    UUID(error["request_id"])
    datetime.fromisoformat(error["timestamp"].replace("Z", "+00:00"))
    assert response.headers["x-request-id"] == error["request_id"]
    assert "traceback" not in response.text.lower()
    return error


@pytest.fixture
def mock_recognizer() -> MockRecognizer:
    recognizer = MockRecognizer()
    recognizer.set_text(zarma_numbers.generate(42), acoustic_score=0.95)
    app.dependency_overrides[get_recognizer] = lambda: recognizer
    try:
        yield recognizer
    finally:
        app.dependency_overrides.pop(get_recognizer, None)


@pytest.fixture
def low_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_RECOGNIZE", "2/minute")
    get_settings.cache_clear()
    limiter.reset()
    try:
        yield
    finally:
        limiter.reset()
        get_settings.cache_clear()


def test_recognize_rate_limit_returns_normalized_429(
    mock_recognizer: MockRecognizer,
    low_rate_limit: None,
) -> None:
    responses = [post_audio() for _ in range(3)]

    assert [response.status_code for response in responses] == [200, 200, 429]
    error = assert_error_envelope(responses[-1], "RATE_LIMITED", 429)
    assert error["message"] == "Too many requests"
    assert ANON_ID not in responses[-1].text


def test_validation_error_is_safe_and_correlated() -> None:
    secret = "person@example.com"
    response = client.post(
        "/api/v1/feedback",
        json={
            "recognition_id": str(uuid4()),
            "anon_id": ANON_ID,
            "feedback_type": secret,
        },
    )

    error = assert_error_envelope(response, "VALIDATION_ERROR", 422)
    assert error["message"] == "Request validation failed"
    assert secret not in response.text
    assert ANON_ID not in response.text


def test_unhandled_exception_returns_safe_500(caplog: pytest.LogCaptureFixture) -> None:
    private_detail = "private SQL /srv/secret.py audio-content"
    hardened_app = create_app()

    @hardened_app.get("/test-unhandled")
    async def fail_safely() -> None:
        raise RuntimeError(private_detail)

    with caplog.at_level("ERROR", logger="zarma.api"):
        response = TestClient(
            hardened_app,
            raise_server_exceptions=False,
        ).get("/test-unhandled")

    error = assert_error_envelope(response, "INTERNAL", 500)
    assert error["message"] == "Internal server error"
    assert private_detail not in response.text
    assert private_detail not in caplog.text
    assert error["request_id"] in caplog.text


def test_recognize_dependency_failure_does_not_leak(
    mock_recognizer: MockRecognizer,
) -> None:
    class FailingRepo:
        async def save(self, *args: object, **kwargs: object) -> object:
            raise RuntimeError("private database statement")

    app.dependency_overrides[get_recognition_repo] = lambda: FailingRepo()
    try:
        response = post_audio()
    finally:
        app.dependency_overrides.pop(get_recognition_repo, None)

    assert_error_envelope(response, "INTERNAL", 500)
    assert "private database statement" not in response.text


def test_anonymous_key_prefers_query_uuid_and_falls_back_to_ip() -> None:
    anon_id = str(uuid4())
    request_with_anon = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": f"anon_id={anon_id}".encode(),
            "client": ("203.0.113.10", 1234),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )
    request_without_anon = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "client": ("203.0.113.10", 1234),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )

    assert anonymous_key(request_with_anon) == anon_id
    assert anonymous_key(request_without_anon) == "203.0.113.10"
