"""Tests de la revue locale et de la génération du manifest dataset (story 4.5)."""

from __future__ import annotations

import asyncio
import json
import math
import struct
import wave
from pathlib import Path
from uuid import UUID, uuid4

from app.dataset.manifest import assign_split, build_manifest
from app.dataset.review import (
    ContributionNotFoundError,
    apply_decision,
    format_pending,
    list_pending,
)
from app.db.models import Consent, Contribution
from app.db.repositories import (
    ContributionRepo,
    InvalidContributionTransitionError,
    speaker_key_for,
)
from app.storage.audio_store import FilesystemAudioStore
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def _write_wav(path: Path, *, channels: int = 1, rate: int = 16_000, width: int = 2) -> None:
    frames = bytearray()
    for index in range(1_600):
        sample = int(8_000 * math.sin(2 * math.pi * 440 * index / 16_000))
        frames.extend(struct.pack("<h", sample) * channels)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(width)
        writer.setframerate(rate)
        writer.writeframes(bytes(frames))


async def _seed_consent(session: AsyncSession, anon_id: UUID) -> UUID:
    consent = Consent(anon_id=str(anon_id), consent_version="v1")
    session.add(consent)
    await session.flush()
    return consent.id


async def _seed(
    session: AsyncSession,
    *,
    anon_id: UUID | None = None,
    status: str = "pending",
    number: int = 42,
    audio_ref: str | None = "unset",
    region: str | None = "Niamey",
    device_info: str | None = "secret-device-model",
) -> Contribution:
    anon_id = anon_id or uuid4()
    consent_id = await _seed_consent(session, anon_id)
    ref = f"{uuid4().hex}.wav" if audio_ref == "unset" else audio_ref
    row = Contribution(
        anon_id=str(anon_id),
        consent_id=consent_id,
        expected_number=number,
        expected_prompt=f"prompt-{number}",
        audio_ref=ref,
        speaker_key=speaker_key_for(anon_id),
        region=region,
        device_info=device_info,
        status=status,
        model_version="mock-1",
        grammar_version="1.0.0",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


# --------------------------------------------------------------------------- #
# Task 1 & 2 — file de revue et transitions
# --------------------------------------------------------------------------- #


def test_pending_queue_excludes_non_pending_and_is_ordered(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def run() -> list[int]:
        async with db_session_factory() as session:
            await _seed(session, status="pending", number=1)
            await _seed(session, status="pending", number=2)
            await _seed(session, status="validated", number=3)
            await _seed(session, status="rejected", number=4)
            await _seed(session, status="withdrawn", number=5)
            items = await list_pending(session)
            return [item.expected_number for item in items]

    numbers = asyncio.run(run())
    assert numbers == [1, 2]


def test_pending_item_carries_no_pii(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def run() -> str:
        async with db_session_factory() as session:
            await _seed(session, region="Dosso", device_info="secret-device-model")
            items = await list_pending(session)
            return format_pending(items)

    rendered = asyncio.run(run())
    assert "secret-device-model" not in rendered
    assert "Dosso" in rendered  # la région coarse est autorisée


def test_apply_decision_is_idempotent_and_explicit(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def run() -> tuple[bool, bool, str]:
        async with db_session_factory() as session:
            row = await _seed(session, status="pending")
            first = await apply_decision(session, row.id, "validate")
            second = await apply_decision(session, row.id, "validate")
            return first.changed, second.changed, second.new_status

    changed_first, changed_second, status = asyncio.run(run())
    assert changed_first is True
    assert changed_second is False
    assert status == "validated"


def test_apply_decision_rejects_withdrawn_and_missing(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def run() -> tuple[bool, bool]:
        async with db_session_factory() as session:
            withdrawn = await _seed(session, status="withdrawn", audio_ref=None)
            terminal = False
            try:
                await apply_decision(session, withdrawn.id, "validate")
            except InvalidContributionTransitionError:
                terminal = True
            missing = False
            try:
                await apply_decision(session, uuid4(), "reject")
            except ContributionNotFoundError:
                missing = True
            return terminal, missing

    terminal, missing = asyncio.run(run())
    assert terminal is True
    assert missing is True


def test_format_pending_reports_audio_presence(
    db_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    store = FilesystemAudioStore(tmp_path / "audio")

    async def run() -> str:
        async with db_session_factory() as session:
            present = await _seed(session)
            await _seed(session, audio_ref=f"{uuid4().hex}.wav")  # missing on disk
            _write_wav(store.local_path(present.audio_ref))
            items = await list_pending(session)
            return format_pending(items, store)

    rendered = asyncio.run(run())
    assert "audio=présent" in rendered
    assert "audio=MANQUANT" in rendered


# --------------------------------------------------------------------------- #
# Task 3 & 4 — sélection, split et manifest
# --------------------------------------------------------------------------- #


def test_manifest_filters_and_is_deterministic(
    db_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    audio_root = tmp_path / "audio"
    store = FilesystemAudioStore(audio_root)
    output = tmp_path / "manifests" / "manifest.jsonl"

    async def prepare() -> None:
        async with db_session_factory() as session:
            # Deux locuteurs validés avec audio canonique -> éligibles.
            for number in (10, 11):
                row = await _seed(session, status="validated", number=number)
                _write_wav(store.local_path(row.audio_ref))
            # Exclus : pending, rejected, withdrawn, validated sans audio.
            await _seed(session, status="pending", number=12)
            await _seed(session, status="rejected", number=13)
            await _seed(session, status="withdrawn", number=14, audio_ref=None)
            no_audio = await _seed(session, status="validated", number=15)
            no_audio.audio_ref = None
            await session.commit()

    async def build() -> tuple[list[dict], str]:
        async with db_session_factory() as session:
            result = await build_manifest(
                session=session,
                audio_root=audio_root,
                output_path=output,
            )
        return result.entries, output.read_text(encoding="utf-8")

    asyncio.run(prepare())
    entries_a, text_a = asyncio.run(build())
    entries_b, text_b = asyncio.run(build())

    assert {entry["expected_number"] for entry in entries_a} == {10, 11}
    assert text_a == text_b  # déterminisme total (contenu identique)
    # Aucun chemin absolu ni PII dans le manifest.
    assert str(audio_root) not in text_a
    for line in text_a.splitlines():
        record = json.loads(line)
        assert "/" not in record["audio_path"]
        assert set(record) == {"audio_path", "expected_number", "speaker_key", "region", "split"}


def test_manifest_fails_closed_on_missing_audio(
    db_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    audio_root = tmp_path / "audio"
    store = FilesystemAudioStore(audio_root)
    output = tmp_path / "manifests" / "manifest.jsonl"

    async def prepare() -> None:
        async with db_session_factory() as session:
            good = await _seed(session, status="validated", number=20)
            _write_wav(store.local_path(good.audio_ref))
            await _seed(session, status="validated", number=21)  # audio absent du disque

    async def build(allow_partial: bool):
        async with db_session_factory() as session:
            return await build_manifest(
                session=session,
                audio_root=audio_root,
                output_path=output,
                allow_partial=allow_partial,
            )

    asyncio.run(prepare())
    strict = asyncio.run(build(False))
    assert strict.written is False
    assert not output.exists()  # aucun manifest partiel publié
    assert any(error.reason == "audio_missing" for error in strict.errors)

    partial = asyncio.run(build(True))
    assert partial.written is True
    assert {entry["expected_number"] for entry in partial.entries} == {20}
    assert output.exists()


def test_manifest_rejects_non_canonical_audio(
    db_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    audio_root = tmp_path / "audio"
    store = FilesystemAudioStore(audio_root)
    output = tmp_path / "manifests" / "manifest.jsonl"

    async def prepare() -> None:
        async with db_session_factory() as session:
            row = await _seed(session, status="validated", number=30)
            _write_wav(store.local_path(row.audio_ref), rate=8_000, channels=2)

    async def build():
        async with db_session_factory() as session:
            return await build_manifest(
                session=session,
                audio_root=audio_root,
                output_path=output,
            )

    asyncio.run(prepare())
    result = asyncio.run(build())
    assert result.written is False
    assert any(error.reason == "audio_not_canonical" for error in result.errors)


def test_split_is_grouped_by_speaker_and_stable() -> None:
    # Un même locuteur tombe toujours dans le même split, quelle que soit la seed.
    speaker = speaker_key_for(uuid4())
    assert assign_split(speaker) == assign_split(speaker)
    # Distribution plausible sur de nombreux locuteurs.
    names = {assign_split(speaker_key_for(uuid4())) for _ in range(200)}
    assert names <= {"train", "dev", "test"}


def test_manifest_never_splits_a_speaker_across_splits(
    db_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    audio_root = tmp_path / "audio"
    store = FilesystemAudioStore(audio_root)
    output = tmp_path / "manifests" / "manifest.jsonl"
    anon = uuid4()

    async def prepare() -> None:
        async with db_session_factory() as session:
            # Deux contributions du MÊME locuteur.
            for number in (40, 41):
                row = await _seed(session, anon_id=anon, status="validated", number=number)
                _write_wav(store.local_path(row.audio_ref))

    async def build():
        async with db_session_factory() as session:
            return await build_manifest(
                session=session,
                audio_root=audio_root,
                output_path=output,
            )

    asyncio.run(prepare())
    result = asyncio.run(build())
    splits_per_speaker: dict[str, set[str]] = {}
    for entry in result.entries:
        splits_per_speaker.setdefault(str(entry["speaker_key"]), set()).add(str(entry["split"]))
    assert all(len(splits) == 1 for splits in splits_per_speaker.values())


def test_repo_predicate_matches_manifest_rows(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def run() -> tuple[int, int]:
        async with db_session_factory() as session:
            await _seed(session, status="validated", number=50)
            await _seed(session, status="validated", number=51, audio_ref=None)
            await _seed(session, status="pending", number=52)
            repo = ContributionRepo(session)
            candidates = await repo.dataset_candidates()
            rows = await repo.dataset_manifest_rows()
            return len(candidates), len(rows)

    candidates, rows = asyncio.run(run())
    assert candidates == 1
    assert rows == 1
