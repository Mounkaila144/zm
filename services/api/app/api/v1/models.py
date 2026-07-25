"""Endpoint ``GET /api/v1/models`` — recognizers ASR disponibles.

Liste les recognizers connus et indique lequel est actif (piloté par
``settings.ASR_MODE``). Les implémentations réelles arrivent en story 2.2 ;
ici on **liste** seulement, sans dépendance ML (API sans GPU).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.asr.base import SpeechRecognizer
from app.asr.factory import get_recognizer
from app.config import Settings, get_settings

#: Recognizers connus du système (ordre stable). Source unique côté API.
AVAILABLE_RECOGNIZERS: tuple[str, ...] = ("mock", "ctc", "llm")

router = APIRouter(tags=["models"])


class ModelsResponse(BaseModel):
    active: str
    available: list[str]


@router.get("/models", response_model=ModelsResponse, summary="Recognizers ASR disponibles")
def list_models(
    settings: Annotated[Settings, Depends(get_settings)],
    _recognizer: Annotated[SpeechRecognizer, Depends(get_recognizer)],
) -> ModelsResponse:
    # La résolution de cette dépendance valide que le mode déclaré actif possède
    # réellement une implémentation utilisable.
    return ModelsResponse(active=settings.ASR_MODE, available=list(AVAILABLE_RECOGNIZERS))
