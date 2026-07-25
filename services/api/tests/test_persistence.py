"""Tests d'intégration SQLite de la persistance, historique et feedback."""

from __future__ import annotations

import asyncio
import wave
from datetime import datetime
from io import BytesIO
from uuid import UUID, uuid4

import app.main as main_module
import pytest
import zarma_numbers
from app.asr.factory import get_recognizer
from app.asr.mock import MockRecognizer
from app.db.models import Feedback, Recognition
from app.db.repositories import get_recognition_repo
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

client = TestClient(app)
ANON_A = "00000000-0000-4000-8000-000000000026"
ANON_B = "00000000-0000-4000-8000-000000000027"


def make_wav() -> bytes:
    output = BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16_000)
        target.writeframes(b"\x00\x00" * 1_600)
    return output.getvalue()


def post_recognition(anon_id: str) -> object:
    return client.post(
        "/api/v1/recognize",
        files={"audio": ("persistence.wav", make_wav(), "audio/wav")},
        data={"anon_id": anon_id},
    )


@pytest.fixture
def mock_recognizer() -> MockRecognizer:
    recognizer = MockRecognizer()
    recognizer.set_text(zarma_numbers.generate(42), acoustic_score=0.95)
    app.dependency_overrides[get_recognizer] = lambda: recognizer
    try:
        yield recognizer
    finally:
        app.dependency_overrides.pop(get_recognizer, None)


def test_recognition_is_persisted_and_returned_by_history(
    mock_recognizer: MockRecognizer,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    response = post_recognition(ANON_A)

    assert response.status_code == 200
    body = response.json()
    recognition_id = UUID(body["id"])
    history = client.get("/api/v1/history", params={"anon_id": ANON_A})

    assert history.status_code == 200
    assert len(history.json()) == 1
    history_item = history.json()[0]
    created_at = history_item.pop("created_at")
    assert history_item == body
    assert datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    assert body["model_version"] == mock_recognizer.model_version
    assert body["grammar_version"] == zarma_numbers.load_lexicon().grammar_version

    async def load_row() -> Recognition:
        async with db_session_factory() as session:
            row = await session.get(Recognition, recognition_id)
            assert row is not None
            return row

    row = asyncio.run(load_row())
    assert row.raw_asr_text == zarma_numbers.generate(42)
    assert row.model_version == body["model_version"]
    assert row.grammar_version == body["grammar_version"]


def test_history_is_isolated_by_anon_id(mock_recognizer: MockRecognizer) -> None:
    response_a = post_recognition(ANON_A)
    response_b = post_recognition(ANON_B)

    history_a = client.get("/api/v1/history", params={"anon_id": ANON_A})

    assert history_a.status_code == 200
    assert [item["id"] for item in history_a.json()] == [response_a.json()["id"]]
    assert response_b.json()["id"] not in {item["id"] for item in history_a.json()}


def test_history_validates_query_and_limit(mock_recognizer: MockRecognizer) -> None:
    assert client.get("/api/v1/history").status_code == 422
    assert client.get("/api/v1/history", params={"anon_id": "invalid"}).status_code == 422
    assert (
        client.get(
            "/api/v1/history",
            params={"anon_id": ANON_A, "limit": 201},
        ).status_code
        == 422
    )


def test_feedback_is_linked_and_inherits_versions(
    mock_recognizer: MockRecognizer,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    recognition = post_recognition(ANON_A).json()
    response = client.post(
        "/api/v1/feedback",
        json={
            "recognition_id": recognition["id"],
            "anon_id": ANON_A,
            "feedback_type": "corrected",
            "proposed_number": 42,
            "corrected_number": 43,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["recognition_id"] == recognition["id"]
    assert body["model_version"] == recognition["model_version"]
    assert body["grammar_version"] == recognition["grammar_version"]

    async def load_feedback() -> Feedback:
        async with db_session_factory() as session:
            row = await session.scalar(select(Feedback).where(Feedback.id == UUID(body["id"])))
            assert row is not None
            return row

    row = asyncio.run(load_feedback())
    assert row.corrected_number == 43
    assert row.recognition_id == UUID(recognition["id"])


def test_unknown_or_foreign_recognition_returns_safe_404(
    mock_recognizer: MockRecognizer,
) -> None:
    recognition = post_recognition(ANON_A).json()
    base_payload = {
        "anon_id": ANON_A,
        "feedback_type": "confirmed",
        "proposed_number": 42,
        "corrected_number": None,
    }

    unknown = client.post(
        "/api/v1/feedback",
        json={"recognition_id": str(uuid4()), **base_payload},
    )
    foreign = client.post(
        "/api/v1/feedback",
        json={
            "recognition_id": recognition["id"],
            **base_payload,
            "anon_id": ANON_B,
        },
    )

    for response in (unknown, foreign):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "RECOGNITION_NOT_FOUND"
        assert "traceback" not in response.text.lower()


def test_database_schema_contains_no_audio_column(db_engine: AsyncEngine) -> None:
    async def column_names() -> dict[str, set[str]]:
        async with db_engine.connect() as connection:
            return await connection.run_sync(
                lambda sync_connection: {
                    table: {
                        column["name"] for column in inspect(sync_connection).get_columns(table)
                    }
                    for table in ("recognitions", "feedbacks")
                }
            )

    columns = asyncio.run(column_names())
    assert all(
        "audio" not in column_name and "bytes" not in column_name
        for table_columns in columns.values()
        for column_name in table_columns
    )


def test_database_failure_is_normalized(
    mock_recognizer: MockRecognizer,
) -> None:
    class FailingRepo:
        async def save(self, *args: object, **kwargs: object) -> object:
            raise RuntimeError("private database detail")

    app.dependency_overrides[get_recognition_repo] = lambda: FailingRepo()
    try:
        response = post_recognition(ANON_A)
    finally:
        app.dependency_overrides.pop(get_recognition_repo, None)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL"
    assert "private database detail" not in response.text
    assert "traceback" not in response.text.lower()


def test_development_lifespan_creates_tables(
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def drop_schema() -> None:
        async with db_engine.begin() as connection:
            await connection.run_sync(main_module.Base.metadata.drop_all)

    asyncio.run(drop_schema())
    monkeypatch.setattr(main_module, "engine", db_engine)

    with TestClient(main_module.create_app()) as lifespan_client:
        assert lifespan_client.get("/health").status_code == 200

    async def table_names() -> set[str]:
        async with db_engine.connect() as connection:
            return await connection.run_sync(
                lambda sync_connection: set(inspect(sync_connection).get_table_names())
            )

    assert asyncio.run(table_names()) >= {"recognitions", "feedbacks"}
