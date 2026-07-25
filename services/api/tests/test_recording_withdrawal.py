"""Tests du retrait réessayable et de ses invariants de confidentialité."""

from __future__ import annotations

import asyncio
import logging
import math
import struct
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from uuid import UUID

import pytest
import zarma_numbers
from app.config import get_settings
from app.consent_text import CONSENT_VERSION
from app.core.rate_limit import limiter
from app.db.models import Consent, Contribution
from app.db.repositories import (
    ContributionRepo,
    InvalidContributionTransitionError,
)
from app.main import app
from app.pipeline.audio import DecodedAudio
from app.storage.audio_store import (
    AudioStorageError,
    FilesystemAudioStore,
    get_audio_store,
)
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

client = TestClient(app)
ANON_A = "00000000-0000-4000-8000-000000000045"
ANON_B = "00000000-0000-4000-8000-000000000046"


def make_wav() -> bytes:
    frames = bytearray()
    for frame_index in range(1_600):
        sample = int(8_000 * math.sin(2 * math.pi * 440 * frame_index / 16_000))
        frames.extend(struct.pack("<h", sample))
    output = BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16_000)
        target.writeframes(frames)
    return output.getvalue()


@pytest.fixture
def audio_storage(tmp_path: Path):
    root = tmp_path / "private-audio"
    store = FilesystemAudioStore(root)
    app.dependency_overrides[get_audio_store] = lambda: store
    try:
        yield root, store
    finally:
        app.dependency_overrides.pop(get_audio_store, None)


def accept_consent(anon_id: str) -> str:
    response = client.post(
        "/api/v1/consent",
        json={"anon_id": anon_id, "consent_version": CONSENT_VERSION},
    )
    assert response.status_code == 201
    return response.json()["id"]


def upload(consent_id: str, anon_id: str, number: int = 42):
    return client.post(
        "/api/v1/recordings",
        files={"audio": ("voice.wav", make_wav(), "audio/wav")},
        data={
            "consent_id": consent_id,
            "anon_id": anon_id,
            "expected_number": str(number),
            "expected_prompt": zarma_numbers.generate(number),
            "grammar_version": zarma_numbers.load_lexicon().grammar_version,
            "region": "Niamey",
            "device_info": "private-device",
        },
    )


def withdraw(anon_id: str):
    return client.post(
        "/api/v1/recordings/withdraw",
        json={"anon_id": anon_id},
    )


async def load_rows(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[list[Consent], list[Contribution]]:
    async with factory() as session:
        consents = list((await session.scalars(select(Consent))).all())
        contributions = list((await session.scalars(select(Contribution))).all())
        return consents, contributions


def test_withdrawal_deletes_all_audio_and_anonymizes_tombstones(
    audio_storage,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root, _store = audio_storage
    consent_ids = [accept_consent(ANON_A), accept_consent(ANON_A)]
    contribution_ids = []
    for index, status in enumerate(("pending", "validated", "rejected")):
        response = upload(consent_ids[index % 2], ANON_A, 40 + index)
        assert response.status_code == 201
        contribution_ids.append(UUID(response.json()["id"]))

        async def set_status(target_status: str = status) -> None:
            async with db_session_factory() as session:
                row = await session.get(Contribution, contribution_ids[-1])
                assert row is not None
                row.status = target_status
                await session.commit()

        asyncio.run(set_status())

    before_consents, before_contributions = asyncio.run(load_rows(db_session_factory))
    original_refs = {row.audio_ref for row in before_contributions}
    original_speakers = {row.speaker_key for row in before_contributions}
    assert len(list(root.glob("*.wav"))) == 3

    response = withdraw(ANON_A)

    assert response.status_code == 200
    assert response.json() == {"status": "withdrawn"}
    assert list(root.glob("*.wav")) == []
    consents, contributions = asyncio.run(load_rows(db_session_factory))
    target_consents = [row for row in consents if str(row.id) in consent_ids]
    assert len(target_consents) == 2
    assert all(row.withdrawn and row.withdrawn_at is not None for row in target_consents)
    assert all(row.anon_id != ANON_A for row in target_consents)
    assert len({row.anon_id for row in target_consents}) == 2

    targets = [row for row in contributions if row.id in contribution_ids]
    assert len(targets) == 3
    assert all(row.status == "withdrawn" for row in targets)
    assert all(row.audio_ref is None for row in targets)
    assert all(row.region is None and row.device_info is None for row in targets)
    assert all(row.anon_id != ANON_A for row in targets)
    assert all(row.speaker_key not in original_speakers for row in targets)
    assert len({row.anon_id for row in targets}) == 3
    assert len({row.speaker_key for row in targets}) == 3
    assert all(reference is not None for reference in original_refs)
    assert {row.expected_number for row in targets} == {40, 41, 42}
    assert {str(row.consent_id) for row in targets} == set(consent_ids)


def test_withdrawal_is_isolated_and_blocks_old_consent(
    audio_storage,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root, _store = audio_storage
    consent_a = accept_consent(ANON_A)
    consent_b = accept_consent(ANON_B)
    contribution_a = upload(consent_a, ANON_A)
    contribution_b = upload(consent_b, ANON_B)
    assert contribution_a.status_code == contribution_b.status_code == 201

    response = withdraw(ANON_A)
    rejected_upload = upload(consent_a, ANON_A, 43)

    assert response.status_code == 200
    assert rejected_upload.status_code == 403
    assert rejected_upload.json()["error"]["code"] == "CONSENT_INVALID"
    consents, contributions = asyncio.run(load_rows(db_session_factory))
    other_consent = next(row for row in consents if str(row.id) == consent_b)
    other_contribution = next(
        row for row in contributions if str(row.id) == contribution_b.json()["id"]
    )
    assert other_consent.anon_id == ANON_B
    assert other_consent.withdrawn is False
    assert other_contribution.anon_id == ANON_B
    assert other_contribution.status == "pending"
    assert other_contribution.audio_ref is not None
    assert (root / other_contribution.audio_ref).exists()


def test_no_contribution_and_repeated_withdrawal_have_same_receipt(
    audio_storage,
) -> None:
    first = withdraw(ANON_A)
    second = withdraw(ANON_A)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {"status": "withdrawn"}
    assert set(first.json()) == {"status"}
    assert ANON_A not in first.text


class _FailOnceStore:
    def __init__(self, delegate: FilesystemAudioStore) -> None:
        self._delegate = delegate
        self._failed = False

    async def save(self, audio: DecodedAudio) -> str:
        return await self._delegate.save(audio)

    async def delete(self, audio_ref: str) -> None:
        if not self._failed:
            self._failed = True
            raise AudioStorageError("private path and storage detail")
        await self._delegate.delete(audio_ref)


def test_partial_storage_failure_revokes_immediately_and_retry_converges(
    audio_storage,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root, store = audio_storage
    consent_id = accept_consent(ANON_A)
    assert upload(consent_id, ANON_A, 50).status_code == 201
    assert upload(consent_id, ANON_A, 51).status_code == 201
    app.dependency_overrides[get_audio_store] = lambda: _FailOnceStore(store)

    failed = withdraw(ANON_A)
    blocked = upload(consent_id, ANON_A, 52)

    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "WITHDRAWAL_INCOMPLETE"
    assert "private path" not in failed.text
    assert blocked.status_code == 403
    consents, contributions = asyncio.run(load_rows(db_session_factory))
    assert all(row.anon_id != ANON_A and row.withdrawn for row in consents)
    active = [row for row in contributions if row.anon_id == ANON_A]
    assert len(active) == 2
    assert all(row.status != "withdrawn" and row.audio_ref is not None for row in active)

    app.dependency_overrides[get_audio_store] = lambda: store
    retried = withdraw(ANON_A)

    assert retried.status_code == 200
    _consents, contributions = asyncio.run(load_rows(db_session_factory))
    assert all(row.status == "withdrawn" for row in contributions)
    assert list(root.glob("*.wav")) == []


def test_final_commit_failure_is_retryable_after_files_are_deleted(
    monkeypatch: pytest.MonkeyPatch,
    audio_storage,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root, _store = audio_storage
    consent_id = accept_consent(ANON_A)
    assert upload(consent_id, ANON_A).status_code == 201
    original = ContributionRepo.finalize_withdrawal

    async def fail_finalization(self, contribution_ids):
        raise RuntimeError("private database detail")

    monkeypatch.setattr(ContributionRepo, "finalize_withdrawal", fail_finalization)
    failed = withdraw(ANON_A)

    assert failed.status_code == 500
    assert failed.json()["error"]["code"] == "INTERNAL"
    assert "private database detail" not in failed.text
    assert list(root.glob("*.wav")) == []
    _consents, contributions = asyncio.run(load_rows(db_session_factory))
    assert contributions[0].status == "pending"
    assert contributions[0].audio_ref is not None

    monkeypatch.setattr(ContributionRepo, "finalize_withdrawal", original)
    retried = withdraw(ANON_A)

    assert retried.status_code == 200
    _consents, contributions = asyncio.run(load_rows(db_session_factory))
    assert contributions[0].status == "withdrawn"
    assert contributions[0].audio_ref is None


class _DelayedStore:
    def __init__(self, delegate: FilesystemAudioStore) -> None:
        self._delegate = delegate
        self.saved = threading.Event()
        self.release = threading.Event()

    async def save(self, audio: DecodedAudio) -> str:
        audio_ref = await self._delegate.save(audio)
        self.saved.set()
        await asyncio.to_thread(self.release.wait)
        return audio_ref

    async def delete(self, audio_ref: str) -> None:
        await self._delegate.delete(audio_ref)


def test_revocation_winning_before_upload_commit_leaves_no_file_or_row(
    audio_storage,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root, store = audio_storage
    consent_id = accept_consent(ANON_A)
    delayed = _DelayedStore(store)
    app.dependency_overrides[get_audio_store] = lambda: delayed

    with ThreadPoolExecutor(max_workers=1) as executor:
        future_upload = executor.submit(upload, consent_id, ANON_A, 60)
        assert delayed.saved.wait(timeout=5)
        withdrawal = withdraw(ANON_A)
        delayed.release.set()
        raced_upload = future_upload.result(timeout=5)

    assert withdrawal.status_code == 200
    assert raced_upload.status_code == 403
    assert raced_upload.json()["error"]["code"] == "CONSENT_INVALID"
    _consents, contributions = asyncio.run(load_rows(db_session_factory))
    assert contributions == []
    assert list(root.glob("*.wav")) == []


def test_dataset_predicate_and_withdrawn_terminality(
    audio_storage,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    consent_id = accept_consent(ANON_A)
    validated = upload(consent_id, ANON_A, 70).json()["id"]
    no_audio = upload(consent_id, ANON_A, 71).json()["id"]
    withdrawn_id = upload(consent_id, ANON_A, 72).json()["id"]

    async def run() -> tuple[list[UUID], bool]:
        async with db_session_factory() as session:
            rows = list((await session.scalars(select(Contribution))).all())
            by_id = {str(row.id): row for row in rows}
            by_id[validated].status = "validated"
            by_id[no_audio].status = "validated"
            by_id[no_audio].audio_ref = None
            by_id[withdrawn_id].status = "withdrawn"
            await session.commit()
            repo = ContributionRepo(session)
            candidates = await repo.dataset_candidates()
            candidate_ids = [row.id for row in candidates]
            terminal = False
            try:
                await repo.update_status(UUID(withdrawn_id), "validated")
            except InvalidContributionTransitionError:
                terminal = True
            return candidate_ids, terminal

    candidates, terminal = asyncio.run(run())
    assert candidates == [UUID(validated)]
    assert terminal is True


def test_withdrawal_rate_limit_and_private_logs(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    audio_storage,
) -> None:
    monkeypatch.setenv("RATE_LIMIT_RECOGNIZE", "2/minute")
    get_settings.cache_clear()
    limiter.reset()
    try:
        with caplog.at_level(logging.INFO, logger="zarma.api"):
            responses = [withdraw(ANON_A) for _ in range(3)]
    finally:
        limiter.reset()
        get_settings.cache_clear()

    assert [response.status_code for response in responses] == [200, 200, 429]
    assert responses[-1].json()["error"]["code"] == "RATE_LIMITED"
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "withdrawal.completed" in logs
    assert ANON_A not in logs
    assert ANON_A not in "".join(response.text for response in responses)


def test_withdrawal_rejects_extra_client_controlled_fields(audio_storage) -> None:
    response = client.post(
        "/api/v1/recordings/withdraw",
        json={
            "anon_id": ANON_A,
            "status": "withdrawn",
            "audio_ref": "attacker-controlled.wav",
            "speaker_key": "attacker-controlled",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "attacker-controlled" not in response.text
