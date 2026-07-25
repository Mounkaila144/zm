"""Tests de l'endpoint interne ``/api/v1/metrics`` (story 4.6).

Sème des ``recognitions`` / ``feedbacks`` en base SQLite temporaire, appelle
``/metrics`` et vérifie : taux (confirmation/correction/rejet), latences
agrégées, couverture linguistique et **absence de PII**.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
import zarma_numbers
from app.db.models import Feedback, Recognition
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

client = TestClient(app)

ANON = "00000000-0000-4000-8000-0000000000f6"
GRAMMAR_VERSION = zarma_numbers.load_lexicon().grammar_version


def _make_recognition(latency_total_ms: int, latency_asr_ms: int) -> Recognition:
    return Recognition(
        id=uuid4(),
        anon_id=ANON,
        recognized_number=42,
        normalized_text="",
        raw_asr_text="",
        confidence=0.9,
        decision="accept",
        alternatives=[],
        model_version="mock-1",
        grammar_version=GRAMMAR_VERSION,
        latency_total_ms=latency_total_ms,
        latency_asr_ms=latency_asr_ms,
    )


def _make_feedback(recognition_id, feedback_type: str) -> Feedback:
    return Feedback(
        id=uuid4(),
        recognition_id=recognition_id,
        anon_id=ANON,
        feedback_type=feedback_type,
        proposed_number=42,
        corrected_number=None,
        model_version="mock-1",
        grammar_version=GRAMMAR_VERSION,
    )


@pytest.fixture
def seeded(db_session_factory: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    """Sème 4 reconnaissances et 4 feedbacks (2 confirmés, 1 corrigé, 1 rejeté)."""

    latencies = [(100, 40), (200, 80), (300, 120), (400, 160)]
    feedback_types = ["confirmed", "confirmed", "corrected", "rejected"]

    async def seed() -> None:
        async with db_session_factory() as session:
            recognitions = [_make_recognition(total, asr) for total, asr in latencies]
            session.add_all(recognitions)
            await session.flush()
            session.add_all(
                _make_feedback(rec.id, feedback_type)
                for rec, feedback_type in zip(recognitions, feedback_types, strict=True)
            )
            await session.commit()

    asyncio.run(seed())
    return {"recognitions": len(latencies), "feedbacks": len(feedback_types)}


def test_metrics_reports_feedback_rates(seeded: dict[str, int]) -> None:
    body = client.get("/api/v1/metrics").json()

    feedback = body["feedback"]
    assert feedback["total_feedbacks"] == 4
    assert feedback["counts"] == {
        "confirmed": 2,
        "corrected": 1,
        "rejected": 1,
        "repeat_requested": 0,
    }
    assert feedback["confirmation_rate"] == 0.5
    assert feedback["correction_rate"] == 0.25
    assert feedback["rejection_rate"] == 0.25
    assert feedback["repeat_rate"] == 0.0


def test_metrics_reports_latency_aggregates(seeded: dict[str, int]) -> None:
    latency = client.get("/api/v1/metrics").json()["latency"]

    assert latency["total"]["count"] == 4
    assert latency["total"]["avg_ms"] == 250.0
    assert latency["total"]["min_ms"] == 100
    assert latency["total"]["max_ms"] == 400
    assert latency["total"]["p50_ms"] == 200
    assert latency["total"]["p95_ms"] == 400

    assert latency["asr"]["count"] == 4
    assert latency["asr"]["avg_ms"] == 100.0
    assert latency["asr"]["min_ms"] == 40
    assert latency["asr"]["max_ms"] == 160


def test_metrics_reports_linguistic_coverage(seeded: dict[str, int]) -> None:
    coverage = client.get("/api/v1/metrics").json()["coverage"]
    info = client.get("/api/v1/grammar/version").json()

    expected_total = info["validated_count"] + len(info["unresolved_items"])
    assert coverage["grammar_version"] == GRAMMAR_VERSION
    assert coverage["validated_count"] == info["validated_count"]
    assert coverage["unresolved_count"] == len(info["unresolved_items"])
    assert coverage["total_items"] == expected_total
    assert 0.0 <= coverage["validated_ratio"] <= 1.0


def test_metrics_are_empty_safe_without_data() -> None:
    """Sans données semées, l'endpoint reste stable (aucune division par zéro)."""

    body = client.get("/api/v1/metrics").json()

    assert body["feedback"]["total_feedbacks"] == 0
    assert body["feedback"]["confirmation_rate"] == 0.0
    assert body["latency"]["total"]["count"] == 0
    assert body["latency"]["total"]["avg_ms"] is None
    assert body["latency"]["total"]["p95_ms"] is None
    # La couverture linguistique ne dépend pas de la base.
    assert body["coverage"]["grammar_version"] == GRAMMAR_VERSION


def test_metrics_contains_no_pii(seeded: dict[str, int]) -> None:
    response = client.get("/api/v1/metrics")

    assert response.status_code == 200
    payload = response.text
    assert ANON not in payload
    assert "anon_id" not in payload
    assert "raw_asr_text" not in payload
    assert "normalized_text" not in payload
