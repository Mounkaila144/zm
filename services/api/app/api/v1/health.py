"""Endpoint de santé ``GET /health``.

Sonde de vivacité minimale (sans dépendance externe) : renvoie ``200`` avec un
statut ``ok``. Utilisée par l'orchestrateur de conteneurs et les checks CI.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str = "ok"


@router.get("/health", response_model=HealthResponse, summary="Sonde de santé")
def health() -> HealthResponse:
    return HealthResponse(status="ok")
