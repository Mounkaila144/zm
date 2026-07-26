"""Endpoints GET/POST /api/v1/consent — consentement versionné (FR19).

``GET`` sert le texte de consentement **courant** et sa version (ressource
versionnée serveur). ``POST`` enregistre une acceptation traçable
(``anon_id`` + ``consent_version`` + horodatage) — prérequis éthique à toute
conservation de voix (FR19/FR20).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from structlog import get_logger

from app.consent_text import current_consent
from app.db.repositories import ConsentRepo, get_consent_repo

router = APIRouter(tags=["consent"])
log = get_logger("zarma.api")


class ConsentAcceptRequest(BaseModel):
    """Acceptation d'un contributeur pour une version de consentement donnée."""

    anon_id: UUID
    consent_version: str = Field(min_length=1, max_length=64)


class ConsentAcceptResponse(BaseModel):
    """Preuve traçable de l'acceptation persistée (version + horodatage)."""

    id: UUID
    anon_id: UUID
    consent_version: str
    accepted_at: datetime
    withdrawn: bool

    model_config = ConfigDict(from_attributes=True)


class ConsentContentResponse(BaseModel):
    """Texte courant et éventuelle acceptation encore valable."""

    consent_version: str
    text: str
    acceptance: ConsentAcceptResponse | None = None


@router.get(
    "/consent",
    response_model=ConsentContentResponse,
    summary="Texte et version de consentement courants",
)
async def get_consent(
    repo: Annotated[ConsentRepo, Depends(get_consent_repo)],
    anon_id: Annotated[UUID | None, Query()] = None,
) -> ConsentContentResponse:
    """Retourne le texte courant et l'accord valable de cet appareil."""
    content = current_consent()
    acceptance = await repo.latest_for(anon_id) if anon_id is not None else None
    if acceptance is not None and (
        acceptance.withdrawn or acceptance.consent_version != content.consent_version
    ):
        acceptance = None
    return ConsentContentResponse(
        consent_version=content.consent_version,
        text=content.text,
        acceptance=(
            ConsentAcceptResponse.model_validate(acceptance) if acceptance is not None else None
        ),
    )


@router.post(
    "/consent",
    response_model=ConsentAcceptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enregistrer l'acceptation d'un consentement versionné",
)
async def accept_consent(
    consent: ConsentAcceptRequest,
    repo: Annotated[ConsentRepo, Depends(get_consent_repo)],
) -> ConsentAcceptResponse:
    """Persiste l'acceptation (version acceptée telle quelle) et l'horodate.

    Journalise uniquement la version acceptée — aucun ``anon_id`` ni donnée
    identifiante (logs sans PII, NFR6).
    """

    row = await repo.save(consent.anon_id, consent.consent_version)
    log.info("consent.accepted", consent_version=consent.consent_version)
    return ConsentAcceptResponse.model_validate(row)


__all__ = [
    "ConsentAcceptRequest",
    "ConsentAcceptResponse",
    "ConsentContentResponse",
    "router",
]
