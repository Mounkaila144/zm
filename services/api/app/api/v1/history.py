"""Endpoint GET /api/v1/history isolé par identifiant anonyme."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

import zarma_numbers
from fastapi import APIRouter, Depends, Query

from app.api.v1.recognize import RecognitionResponse
from app.db.repositories import RecognitionRepo, get_recognition_repo

router = APIRouter(tags=["history"])


class HistoryRecognitionResponse(RecognitionResponse):
    """Reconnaissance historisée avec sa date de persistance."""

    created_at: datetime


@router.get(
    "/history",
    response_model=list[HistoryRecognitionResponse],
    summary="Historique des reconnaissances anonymes",
)
async def history(
    anon_id: Annotated[UUID, Query(description="Anonymous device UUID")],
    repo: Annotated[RecognitionRepo, Depends(get_recognition_repo)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[HistoryRecognitionResponse]:
    """Retourne uniquement les reconnaissances du device demandé."""

    rows = await repo.history(anon_id, limit)
    return [
        HistoryRecognitionResponse(
            id=row.id,
            recognized_number=row.recognized_number,
            zarma_text=(
                row.expression["zarma_text"]
                if row.expression
                else (
                    zarma_numbers.generate(row.recognized_number)
                    if row.recognized_number is not None
                    else ""
                )
            ),
            normalized_text=row.normalized_text,
            confidence=row.confidence,
            decision=row.decision,
            alternatives=row.alternatives,
            expression=row.expression,
            model_version=row.model_version,
            grammar_version=row.grammar_version,
            latency_total_ms=row.latency_total_ms or 0,
            latency_asr_ms=row.latency_asr_ms or 0,
            created_at=row.created_at,
        )
        for row in rows
    ]


__all__ = ["HistoryRecognitionResponse", "router"]
