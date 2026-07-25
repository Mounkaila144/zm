"""Endpoint POST /api/v1/feedback."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.core.errors import ApiError, api_error_response, request_id_from
from app.core.rate_limit import limiter, recognize_limit
from app.db.repositories import (
    FeedbackRepo,
    RecognitionNotFoundError,
    get_feedback_repo,
)

router = APIRouter(tags=["feedback"])
FeedbackType = Literal["confirmed", "corrected", "rejected", "repeat_requested"]


class FeedbackRequest(BaseModel):
    recognition_id: UUID
    anon_id: UUID
    feedback_type: FeedbackType
    proposed_number: int | None = None
    corrected_number: int | None = None


class FeedbackResponse(BaseModel):
    id: UUID
    recognition_id: UUID
    anon_id: UUID
    feedback_type: FeedbackType
    proposed_number: int | None
    corrected_number: int | None
    model_version: str
    grammar_version: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enregistrer un feedback de reconnaissance",
    responses={
        404: {"model": ApiError, "description": "Recognition not found"},
    },
)
@limiter.limit(recognize_limit)
async def create_feedback(
    request: Request,
    feedback: FeedbackRequest,
    repo: Annotated[FeedbackRepo, Depends(get_feedback_repo)],
) -> FeedbackResponse | JSONResponse:
    """Persiste un feedback sans exposer de détail interne."""

    try:
        row = await repo.save(feedback)
    except RecognitionNotFoundError:
        return api_error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="RECOGNITION_NOT_FOUND",
            message="Recognition not found",
            request_id=request_id_from(request),
        )
    return FeedbackResponse.model_validate(row)


__all__ = ["FeedbackRequest", "FeedbackResponse", "router"]
