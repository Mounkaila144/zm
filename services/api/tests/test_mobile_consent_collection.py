"""Gardes de version et collecte des calculs explicitement consentie."""

from __future__ import annotations

import asyncio
import wave
from io import BytesIO
from pathlib import Path
from uuid import UUID

import zarma_numbers
from app.asr.factory import get_recognizer
from app.asr.mock import MockRecognizer
from app.config import get_settings
from app.consent_text import CONSENT_VERSION
from app.db.models import Contribution
from app.main import app
from app.storage.audio_store import FilesystemAudioStore, get_audio_store
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

client = TestClient(app)
ANON_ID = "00000000-0000-4000-8000-000000000088"


def _wav() -> bytes:
    output = BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16_000)
        target.writeframes(b"\x00\x00" * 16_000)
    return output.getvalue()


def _enable_production_guards(monkeypatch) -> None:
    monkeypatch.setenv("MOBILE_ENFORCE_MIN_BUILD", "true")
    monkeypatch.setenv("MOBILE_MIN_SUPPORTED_BUILD", "2")
    monkeypatch.setenv("MOBILE_LATEST_BUILD", "2")
    monkeypatch.setenv("REQUIRE_TRAINING_CONSENT", "true")
    get_settings.cache_clear()


def test_mobile_config_and_old_build_are_blocked(monkeypatch) -> None:
    _enable_production_guards(monkeypatch)

    policy = client.get("/api/v1/mobile/config")
    assert policy.status_code == 200
    assert policy.json()["minimum_supported_build"] == 2

    blocked = client.post("/api/v1/recognize")
    assert blocked.status_code == 426
    assert blocked.json()["error"]["code"] == "APP_UPDATE_REQUIRED"

    current = client.post(
        "/api/v1/recognize",
        headers={"X-App-Build": "2"},
    )
    assert current.status_code == 422


def test_calculation_audio_requires_consent_and_becomes_training_candidate(
    monkeypatch,
    tmp_path: Path,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _enable_production_guards(monkeypatch)
    store = FilesystemAudioStore(tmp_path / "private-audio")
    recognizer = MockRecognizer()
    recognizer.set_text(zarma_numbers.generate(42), acoustic_score=0.95)
    app.dependency_overrides[get_audio_store] = lambda: store
    app.dependency_overrides[get_recognizer] = lambda: recognizer

    try:
        refused = client.post(
            "/api/v1/recognize",
            headers={"X-App-Build": "2"},
            files={"audio": ("calculation.wav", _wav(), "audio/wav")},
            data={"anon_id": ANON_ID},
        )
        assert refused.status_code == 403
        assert refused.json()["error"]["code"] == "CONSENT_INVALID"

        accepted = client.post(
            "/api/v1/consent",
            json={
                "anon_id": ANON_ID,
                "consent_version": CONSENT_VERSION,
            },
        )
        assert accepted.status_code == 201
        consent_id = accepted.json()["id"]

        restored = client.get(
            "/api/v1/consent",
            params={"anon_id": ANON_ID},
        )
        assert restored.status_code == 200
        assert restored.json()["acceptance"]["id"] == consent_id

        recognized = client.post(
            "/api/v1/recognize",
            headers={"X-App-Build": "2"},
            files={"audio": ("calculation.wav", _wav(), "audio/wav")},
            data={"anon_id": ANON_ID, "consent_id": consent_id},
        )
        assert recognized.status_code == 200, recognized.text
        recognition_id = recognized.json()["id"]

        async def load_contribution() -> Contribution:
            async with db_session_factory() as session:
                row = await session.scalar(
                    select(Contribution).where(Contribution.recognition_id == UUID(recognition_id))
                )
                assert row is not None
                return row

        contribution = asyncio.run(load_contribution())
        assert contribution is not None
        assert contribution.source == "calculation"
        assert contribution.status == "pending"
        assert contribution.expected_prompt == zarma_numbers.generate(42)
        assert contribution.audio_ref is not None
        audio_path = store.local_path(contribution.audio_ref)
        assert audio_path.is_file()

        confirmed = client.post(
            "/api/v1/feedback",
            json={
                "recognition_id": recognition_id,
                "anon_id": ANON_ID,
                "feedback_type": "confirmed",
                "proposed_number": 42,
                "corrected_number": None,
            },
        )
        assert confirmed.status_code == 201

        async def status() -> str:
            async with db_session_factory() as session:
                row = await session.get(Contribution, contribution.id)
                assert row is not None
                return row.status

        assert asyncio.run(status()) == "validated"

        withdrawn = client.post(
            "/api/v1/recordings/withdraw",
            json={"anon_id": ANON_ID},
        )
        assert withdrawn.status_code == 200
        assert not audio_path.exists()
        revoked = client.get(
            "/api/v1/consent",
            params={"anon_id": ANON_ID},
        )
        assert revoked.status_code == 200
        assert revoked.json()["acceptance"] is None
    finally:
        app.dependency_overrides.pop(get_audio_store, None)
        app.dependency_overrides.pop(get_recognizer, None)
