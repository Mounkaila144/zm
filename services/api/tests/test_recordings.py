"""Tests d'intégration de l'upload consenti de contributions (story 4.3)."""

from __future__ import annotations

import asyncio
import logging
import math
import os
import sqlite3
import struct
import subprocess
import sys
import wave
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import zarma_numbers
from app.api.v1 import recordings as recordings_route
from app.config import get_settings
from app.consent_text import CONSENT_VERSION
from app.core.rate_limit import limiter
from app.db.models import Consent, Contribution
from app.db.repositories import (
    ContributionRepo,
    get_contribution_repo,
    speaker_key_for,
)
from app.main import app
from app.pipeline.audio import MAX_AUDIO_SIZE
from app.storage.audio_store import (
    AudioStorageError,
    FilesystemAudioStore,
    get_audio_store,
)
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

client = TestClient(app)
ANON_A = "00000000-0000-4000-8000-000000000043"
ANON_B = "00000000-0000-4000-8000-000000000044"


def make_wav(
    *,
    channels: int = 1,
    sample_rate: int = 16_000,
    duration_ms: int = 100,
) -> bytes:
    frame_count = sample_rate * duration_ms // 1000
    frames = bytearray()
    for frame_index in range(frame_count):
        sample = int(8_000 * math.sin(2 * math.pi * 440 * frame_index / sample_rate))
        for channel_index in range(channels):
            frames.extend(struct.pack("<h", sample // (channel_index + 1)))

    output = BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        target.writeframes(frames)
    return output.getvalue()


@pytest.fixture
def audio_root(tmp_path: Path) -> Path:
    root = tmp_path / "private-audio"
    app.dependency_overrides[get_audio_store] = lambda: FilesystemAudioStore(root)
    try:
        yield root
    finally:
        app.dependency_overrides.pop(get_audio_store, None)


def accept_consent(
    anon_id: str = ANON_A,
    consent_version: str = CONSENT_VERSION,
) -> str:
    response = client.post(
        "/api/v1/consent",
        json={"anon_id": anon_id, "consent_version": consent_version},
    )
    assert response.status_code == 201
    return response.json()["id"]


def post_recording(
    *,
    consent_id: str,
    anon_id: str = ANON_A,
    expected_number: int = 42,
    expected_prompt: str | None = None,
    grammar_version: str | None = None,
    audio: bytes | None = None,
    filename: str = "contribution.wav",
    mime_type: str = "audio/wav",
    region: str | None = "Niamey",
    device_info: str | None = "test-device",
):
    data = {
        "consent_id": consent_id,
        "anon_id": anon_id,
        "expected_number": str(expected_number),
        "expected_prompt": expected_prompt or zarma_numbers.generate(expected_number),
        "grammar_version": grammar_version or zarma_numbers.load_lexicon().grammar_version,
    }
    if region is not None:
        data["region"] = region
    if device_info is not None:
        data["device_info"] = device_info
    return client.post(
        "/api/v1/recordings",
        files={
            "audio": (
                filename,
                make_wav() if audio is None else audio,
                mime_type,
            )
        },
        data=data,
    )


async def load_contributions(
    factory: async_sessionmaker[AsyncSession],
) -> list[Contribution]:
    async with factory() as session:
        return list((await session.scalars(select(Contribution))).all())


def error_code(response) -> str:
    return response.json()["error"]["code"]


def test_valid_upload_normalizes_audio_and_persists_safe_metadata(
    audio_root: Path,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    consent_id = accept_consent()

    response = post_recording(
        consent_id=consent_id,
        audio=make_wav(channels=2, sample_rate=44_100),
        filename="../../private-name.wav",
    )

    assert response.status_code == 201
    receipt = response.json()
    assert set(receipt) == {
        "id",
        "status",
        "expected_number",
        "expected_prompt",
        "model_version",
        "grammar_version",
        "created_at",
    }
    assert receipt["status"] == "pending"
    assert receipt["expected_number"] == 42
    assert receipt["expected_prompt"] == zarma_numbers.generate(42)
    assert ANON_A not in response.text
    assert consent_id not in response.text
    assert "audio_ref" not in response.text
    assert "private-name" not in response.text

    rows = asyncio.run(load_contributions(db_session_factory))
    assert len(rows) == 1
    row = rows[0]
    assert str(row.id) == receipt["id"]
    assert row.anon_id == ANON_A
    assert str(row.consent_id) == consent_id
    assert row.speaker_key == speaker_key_for(UUID(ANON_A))
    assert row.region == "Niamey"
    assert row.device_info == "test-device"
    assert row.model_version == receipt["model_version"]
    assert row.grammar_version == receipt["grammar_version"]
    assert row.audio_ref is not None
    assert "/" not in row.audio_ref and "\\" not in row.audio_ref

    stored = audio_root / row.audio_ref
    assert stored.exists()
    with wave.open(str(stored), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getframerate() == 16_000
        assert wav_file.getsampwidth() == 2
        assert wav_file.getnframes() > 0
    assert stored.stat().st_mode & 0o777 == 0o600
    assert audio_root.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("case", ["unknown", "other-anon", "outdated", "withdrawn"])
def test_invalid_consent_returns_same_generic_403_without_collecting(
    case: str,
    audio_root: Path,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if case == "unknown":
        consent_id = str(uuid4())
        anon_id = ANON_A
    elif case == "other-anon":
        consent_id = accept_consent(ANON_A)
        anon_id = ANON_B
    elif case == "outdated":
        consent_id = accept_consent(ANON_A, "0.9.0")
        anon_id = ANON_A
    else:
        consent_id = accept_consent(ANON_A)
        anon_id = ANON_A

        async def withdraw() -> None:
            async with db_session_factory() as session:
                row = await session.get(Consent, UUID(consent_id))
                assert row is not None
                row.withdrawn = True
                await session.commit()

        asyncio.run(withdraw())

    response = post_recording(consent_id=consent_id, anon_id=anon_id)

    assert response.status_code == 403
    assert error_code(response) == "CONSENT_INVALID"
    assert response.json()["error"]["message"] == "Valid consent required"
    assert asyncio.run(load_contributions(db_session_factory)) == []
    assert not audio_root.exists() or list(audio_root.iterdir()) == []


@pytest.mark.parametrize(
    ("audio", "mime_type", "status_code", "code"),
    [
        (b"", "audio/wav", 422, "AUDIO_INVALID"),
        (b"not-a-wave", "audio/wav", 422, "AUDIO_INVALID"),
        (make_wav()[:-10], "audio/wav", 422, "AUDIO_INVALID"),
        (make_wav(), "image/png", 422, "AUDIO_INVALID"),
        (b"x" * (MAX_AUDIO_SIZE + 1), "audio/wav", 413, "FILE_TOO_LARGE"),
    ],
)
def test_invalid_audio_never_creates_file_or_row(
    audio: bytes,
    mime_type: str,
    status_code: int,
    code: str,
    audio_root: Path,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    response = post_recording(
        consent_id=accept_consent(),
        audio=audio,
        mime_type=mime_type,
    )

    assert response.status_code == status_code
    assert error_code(response) == code
    assert asyncio.run(load_contributions(db_session_factory)) == []
    assert not audio_root.exists() or list(audio_root.iterdir()) == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"expected_number": -1, "expected_prompt": "invalid"},
        {"expected_number": 1_000_001, "expected_prompt": "invalid"},
        {"expected_prompt": "texte client falsifié"},
        {"grammar_version": "obsolete"},
        {"region": "x" * 129},
        {"device_info": "x" * 257},
    ],
)
def test_invalid_metadata_never_creates_file_or_row(
    overrides: dict[str, object],
    audio_root: Path,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    response = post_recording(consent_id=accept_consent(), **overrides)

    assert response.status_code == 422
    assert error_code(response) in {"METADATA_INVALID", "VALIDATION_ERROR"}
    assert asyncio.run(load_contributions(db_session_factory)) == []
    assert not audio_root.exists() or list(audio_root.iterdir()) == []


class FailingStore:
    async def save(self, _audio) -> str:
        raise AudioStorageError("private storage detail")

    async def delete(self, _audio_ref: str) -> None:
        raise AssertionError("delete should not run when save failed")


class FailingContributionRepo:
    async def save(self, _contribution) -> Contribution:
        raise RuntimeError("private database detail")


def test_storage_failure_is_safe_and_does_not_persist(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app.dependency_overrides[get_audio_store] = lambda: FailingStore()
    try:
        response = post_recording(consent_id=accept_consent())
    finally:
        app.dependency_overrides.pop(get_audio_store, None)

    assert response.status_code == 503
    assert error_code(response) == "STORAGE_UNAVAILABLE"
    assert "private storage detail" not in response.text
    assert asyncio.run(load_contributions(db_session_factory)) == []


def test_database_failure_compensates_the_saved_file(
    audio_root: Path,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app.dependency_overrides[get_contribution_repo] = lambda: FailingContributionRepo()
    try:
        response = post_recording(consent_id=accept_consent())
    finally:
        app.dependency_overrides.pop(get_contribution_repo, None)

    assert response.status_code == 500
    assert error_code(response) == "INTERNAL"
    assert asyncio.run(load_contributions(db_session_factory)) == []
    assert audio_root.exists()
    assert list(audio_root.iterdir()) == []


def test_filesystem_delete_is_idempotent_and_rejects_traversal(tmp_path: Path) -> None:
    store = FilesystemAudioStore(tmp_path / "audio")

    asyncio.run(store.delete("missing.wav"))
    asyncio.run(store.delete("missing.wav"))
    with pytest.raises(AudioStorageError):
        asyncio.run(store.delete("../outside.wav"))
    with pytest.raises(AudioStorageError):
        asyncio.run(store.delete(str(tmp_path / "outside.wav")))


def test_speaker_key_is_stable_and_separates_anonymous_speakers() -> None:
    assert speaker_key_for(UUID(ANON_A)) == speaker_key_for(UUID(ANON_A))
    assert speaker_key_for(UUID(ANON_A)) != speaker_key_for(UUID(ANON_B))
    assert ANON_A not in speaker_key_for(UUID(ANON_A))


def test_recording_rate_limit_uses_shared_configured_quota(
    monkeypatch: pytest.MonkeyPatch,
    audio_root: Path,
) -> None:
    monkeypatch.setenv("RATE_LIMIT_RECOGNIZE", "2/minute")
    get_settings.cache_clear()
    limiter.reset()
    try:
        consent_id = accept_consent()
        responses = [post_recording(consent_id=consent_id) for _ in range(3)]
    finally:
        limiter.reset()
        get_settings.cache_clear()

    assert [response.status_code for response in responses] == [201, 201, 429]
    assert error_code(responses[-1]) == "RATE_LIMITED"
    assert ANON_A not in responses[-1].text
    assert len(list(audio_root.glob("*.wav"))) == 2


def test_recording_logs_and_receipt_do_not_disclose_sensitive_values(
    caplog: pytest.LogCaptureFixture,
    audio_root: Path,
) -> None:
    consent_id = accept_consent()
    secret_device = "private-device-fingerprint"

    with caplog.at_level(logging.INFO, logger="zarma.api"):
        response = post_recording(
            consent_id=consent_id,
            device_info=secret_device,
        )

    assert response.status_code == 201
    logged = "\n".join(record.getMessage() for record in caplog.records)
    for secret in (ANON_A, consent_id, secret_device, str(audio_root)):
        assert secret not in logged
        assert secret not in response.text


def test_upload_file_is_closed_on_success(
    monkeypatch: pytest.MonkeyPatch,
    audio_root: Path,
) -> None:
    uploads = []
    original = recordings_route.validate_and_decode

    async def capture_upload(upload):
        uploads.append(upload)
        return await original(upload)

    monkeypatch.setattr(recordings_route, "validate_and_decode", capture_upload)

    response = post_recording(consent_id=accept_consent())

    assert response.status_code == 201
    assert len(uploads) == 1
    assert uploads[0].file.closed is True


def test_contribution_schema_has_indexes_fk_and_no_binary_column(
    db_engine: AsyncEngine,
) -> None:
    async def schema_details():
        async with db_engine.connect() as connection:
            return await connection.run_sync(
                lambda sync_connection: (
                    inspect(sync_connection).get_columns("contributions"),
                    inspect(sync_connection).get_indexes("contributions"),
                    inspect(sync_connection).get_foreign_keys("contributions"),
                )
            )

    columns, indexes, foreign_keys = asyncio.run(schema_details())
    names = {column["name"] for column in columns}
    assert {"audio_ref", "speaker_key", "status", "model_version"} <= names
    assert all(
        "blob" not in str(column["type"]).lower() and "binary" not in str(column["type"]).lower()
        for column in columns
    )
    assert {"idx_contrib_speaker", "idx_contrib_status"} <= {index["name"] for index in indexes}
    assert any(
        foreign_key["referred_table"] == "consents"
        and foreign_key["constrained_columns"] == ["consent_id"]
        for foreign_key in foreign_keys
    )


def test_contribution_repo_rejects_missing_audio_reference(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def run() -> None:
        async with db_session_factory() as session:
            repo = ContributionRepo(session)
            from app.db.repositories import ContributionCreate

            with pytest.raises(ValueError):
                await repo.save(
                    ContributionCreate(
                        anon_id=UUID(ANON_A),
                        consent_id=uuid4(),
                        expected_number=42,
                        expected_prompt=zarma_numbers.generate(42),
                        audio_ref="",
                        region=None,
                        device_info=None,
                        model_version="test",
                        grammar_version=zarma_numbers.load_lexicon().grammar_version,
                    )
                )

    asyncio.run(run())


def test_contribution_migration_upgrade_downgrade_and_check(
    tmp_path: Path,
) -> None:
    api_root = Path(__file__).resolve().parents[1]
    database = tmp_path / "alembic.db"
    environment = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{database}",
    }

    def alembic(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "alembic.ini",
                *arguments,
            ],
            cwd=api_root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )

    alembic("upgrade", "head")
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert "contributions" in tables

    alembic("downgrade", "20260724_0002")
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert "contributions" not in tables

    alembic("upgrade", "head")
    result = alembic("check")
    assert "No new upgrade operations detected" in result.stdout
