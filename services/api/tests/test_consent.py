"""Tests d'intégration du consentement versionné (story 4.1).

Couvre : ``GET /consent`` (texte + version courants), ``POST /consent``
(201 + persistance version/horodatage/anon_id), traçabilité (relecture) et
journalisation sans PII.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

import pytest
from app.consent_text import CONSENT_TEXT, CONSENT_VERSION
from app.db.models import Consent
from app.db.repositories import ConsentRepo
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

client = TestClient(app)
ANON_A = "00000000-0000-4000-8000-000000000041"
ANON_B = "00000000-0000-4000-8000-000000000042"


def test_get_consent_returns_current_version_and_text() -> None:
    response = client.get("/api/v1/consent")

    assert response.status_code == 200
    body = response.json()
    assert body["consent_version"] == CONSENT_VERSION
    assert body["text"] == CONSENT_TEXT
    # AC1 : les quatre points requis sont présents dans le texte.
    for required in ("Usage", "Anonymat", "Conservation", "Retrait"):
        assert required in body["text"]


def test_post_consent_persists_version_timestamp_and_anon_id(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    response = client.post(
        "/api/v1/consent",
        json={"anon_id": ANON_A, "consent_version": CONSENT_VERSION},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["anon_id"] == ANON_A
    assert body["consent_version"] == CONSENT_VERSION
    assert body["withdrawn"] is False
    assert body["accepted_at"] is not None
    consent_id = UUID(body["id"])

    async def load_row() -> Consent:
        async with db_session_factory() as session:
            row = await session.get(Consent, consent_id)
            assert row is not None
            return row

    row = asyncio.run(load_row())
    assert row.anon_id == ANON_A
    assert row.consent_version == CONSENT_VERSION
    assert row.accepted_at is not None
    assert row.withdrawn is False
    assert row.withdrawn_at is None


def test_accepted_consent_is_traceable_by_version_and_timestamp(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # AC4 : une acceptation reste traçable (version acceptée telle quelle +
    # horodatage), même si le texte courant venait à évoluer.
    accepted = client.post(
        "/api/v1/consent",
        json={"anon_id": ANON_A, "consent_version": "0.9.0"},
    ).json()

    async def load_for_anon() -> Consent:
        async with db_session_factory() as session:
            row = await session.scalar(select(Consent).where(Consent.anon_id == ANON_A))
            assert row is not None
            return row

    row = asyncio.run(load_for_anon())
    assert row.consent_version == "0.9.0"
    assert str(row.id) == accepted["id"]


def test_post_consent_validates_anon_id() -> None:
    response = client.post(
        "/api/v1/consent",
        json={"anon_id": "not-a-uuid", "consent_version": CONSENT_VERSION},
    )
    assert response.status_code == 422


def test_consent_logging_has_no_pii(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="zarma.api"):
        response = client.post(
            "/api/v1/consent",
            json={"anon_id": ANON_B, "consent_version": CONSENT_VERSION},
        )

    assert response.status_code == 201
    logged = "\n".join(record.getMessage() for record in caplog.records)
    # La version acceptée est journalisée pour l'audit…
    assert "consent.accepted" in logged
    # …mais jamais l'identifiant du contributeur (NFR6 : logs sans PII).
    assert ANON_B not in logged


def test_consent_guard_gates_collection(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # AC3 / Task 5 : socle du guard « pas de collecte sans consentement ».
    # L'upload consenti (story 4.3) exigera `require_valid_consent` ; ici on
    # valide que le prérequis est absent avant acceptation et présent après.
    anon = UUID(ANON_A)

    async def run() -> tuple[bool, bool]:
        async with db_session_factory() as session:
            repo = ConsentRepo(session)
            before = await repo.has_valid_consent(anon)
            await repo.save(anon, CONSENT_VERSION)
            after = await repo.has_valid_consent(anon)
            return before, after

    before, after = asyncio.run(run())
    assert before is False
    assert after is True


def test_consent_guard_rejects_an_outdated_or_withdrawn_consent(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    anon = UUID(ANON_A)

    async def run() -> tuple[bool, bool]:
        async with db_session_factory() as session:
            repo = ConsentRepo(session)
            await repo.save(anon, "0.9.0")
            outdated = await repo.has_valid_consent(anon)

            current = await repo.save(anon, CONSENT_VERSION)
            current.withdrawn = True
            await session.commit()
            withdrawn = await repo.has_valid_consent(anon)
            return outdated, withdrawn

    outdated, withdrawn = asyncio.run(run())
    assert outdated is False
    assert withdrawn is False


def test_post_consent_rejects_an_empty_version() -> None:
    response = client.post(
        "/api/v1/consent",
        json={"anon_id": ANON_A, "consent_version": ""},
    )
    assert response.status_code == 422


def test_consents_table_has_no_audio_column(db_engine: AsyncEngine) -> None:
    async def column_names() -> set[str]:
        async with db_engine.connect() as connection:
            return await connection.run_sync(
                lambda sync_connection: {
                    column["name"] for column in inspect(sync_connection).get_columns("consents")
                }
            )

    columns = asyncio.run(column_names())
    assert all("audio" not in name and "bytes" not in name for name in columns)
