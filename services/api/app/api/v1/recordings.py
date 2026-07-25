"""Upload sécurisé de contributions vocales explicitement consenties."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

import zarma_numbers
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from structlog import get_logger

from app.asr.base import SpeechRecognizer
from app.asr.factory import get_recognizer
from app.core.consent import InvalidConsentError, require_valid_consent
from app.core.errors import ApiError, api_error_response, request_id_from
from app.core.rate_limit import limiter, recognize_limit
from app.db.repositories import (
    ConsentRepo,
    ContributionConsentInvalidError,
    ContributionCreate,
    ContributionRepo,
    get_consent_repo,
    get_contribution_repo,
)
from app.pipeline.audio import (
    MAX_AUDIO_SIZE,
    AudioValidationError,
    validate_and_decode,
)
from app.services.withdrawal import WithdrawalIncompleteError, WithdrawalService
from app.storage.audio_store import AudioStorageError, AudioStore, get_audio_store

router = APIRouter(tags=["recordings"])
log = get_logger("zarma.api")


class RecordingReceipt(BaseModel):
    """Reçu public sans référence de stockage ni identité anonyme."""

    id: UUID
    status: Literal["pending"]
    expected_number: int
    expected_prompt: str
    model_version: str
    grammar_version: str
    created_at: datetime

    model_config = {"protected_namespaces": (), "from_attributes": True}


class RecordingMetadataError(Exception):
    """Métadonnées client incompatibles avec les sources serveur."""


class WithdrawalRequest(BaseModel):
    """Commande minimale de retrait, sans identifiant de contribution."""

    anon_id: UUID

    model_config = {"extra": "forbid"}


class WithdrawalReceipt(BaseModel):
    """Reçu générique qui ne révèle ni existence ni volume de données."""

    status: Literal["withdrawn"]


@router.post(
    "/recordings",
    response_model=RecordingReceipt,
    status_code=status.HTTP_201_CREATED,
    summary="Stocker une contribution vocale consentie",
    responses={
        403: {"model": ApiError, "description": "Consentement invalide"},
        413: {"model": ApiError, "description": "Fichier trop volumineux"},
        422: {"model": ApiError, "description": "Audio ou métadonnées invalides"},
        429: {"model": ApiError, "description": "Quota dépassé"},
        500: {"model": ApiError, "description": "Erreur interne"},
        503: {"model": ApiError, "description": "Stockage indisponible"},
    },
)
@limiter.limit(recognize_limit)
async def create_recording(
    request: Request,
    audio: Annotated[
        UploadFile,
        File(description=f"WAV audio, maximum {MAX_AUDIO_SIZE // 1_000_000} MB"),
    ],
    consent_id: Annotated[UUID, Form(description="Accepted consent UUID")],
    anon_id: Annotated[UUID, Form(description="Anonymous device UUID")],
    expected_number: Annotated[int, Form(ge=0, le=1_000_000)],
    expected_prompt: Annotated[str, Form(min_length=1, max_length=512)],
    grammar_version: Annotated[str, Form(min_length=1, max_length=64)],
    consent_repo: Annotated[ConsentRepo, Depends(get_consent_repo)],
    contribution_repo: Annotated[
        ContributionRepo,
        Depends(get_contribution_repo),
    ],
    store: Annotated[AudioStore, Depends(get_audio_store)],
    recognizer: Annotated[SpeechRecognizer, Depends(get_recognizer)],
    region: Annotated[str | None, Form(max_length=128)] = None,
    device_info: Annotated[str | None, Form(max_length=256)] = None,
) -> RecordingReceipt | JSONResponse:
    """Valide complètement, stocke le WAV, puis persiste les métadonnées."""

    request_id = request_id_from(request)
    audio_ref: str | None = None
    try:
        await require_valid_consent(
            repo=consent_repo,
            consent_id=consent_id,
            anon_id=anon_id,
        )
        lexicon = zarma_numbers.load_lexicon()
        if grammar_version != lexicon.grammar_version:
            raise RecordingMetadataError
        try:
            canonical_prompt = zarma_numbers.generate(expected_number)
        except (
            zarma_numbers.OutOfRangeError,
            zarma_numbers.UnresolvedFormError,
        ) as exc:
            raise RecordingMetadataError from exc
        if expected_prompt != canonical_prompt:
            raise RecordingMetadataError

        decoded_audio = await validate_and_decode(audio)
        audio_ref = await store.save(decoded_audio)
        try:
            row = await contribution_repo.save(
                ContributionCreate(
                    anon_id=anon_id,
                    consent_id=consent_id,
                    expected_number=expected_number,
                    expected_prompt=canonical_prompt,
                    audio_ref=audio_ref,
                    region=region,
                    device_info=device_info,
                    model_version=recognizer.model_version,
                    grammar_version=lexicon.grammar_version,
                )
            )
        except Exception:
            await store.delete(audio_ref)
            audio_ref = None
            raise

        log.info(
            "recording.created",
            request_id=request_id,
            status="pending",
        )
        return RecordingReceipt.model_validate(row)
    except (InvalidConsentError, ContributionConsentInvalidError):
        return api_error_response(
            status_code=status.HTTP_403_FORBIDDEN,
            code="CONSENT_INVALID",
            message="Valid consent required",
            request_id=request_id,
        )
    except RecordingMetadataError:
        return api_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="METADATA_INVALID",
            message="Contribution metadata is invalid",
            request_id=request_id,
        )
    except AudioValidationError as exc:
        return api_error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            request_id=request_id,
        )
    except AudioStorageError:
        return api_error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="STORAGE_UNAVAILABLE",
            message="Audio storage is unavailable",
            request_id=request_id,
        )
    except Exception:
        if audio_ref is not None:
            try:
                await store.delete(audio_ref)
            except AudioStorageError:
                pass
        return api_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL",
            message="Internal recording error",
            request_id=request_id,
        )
    finally:
        await audio.close()


@router.post(
    "/recordings/withdraw",
    response_model=WithdrawalReceipt,
    summary="Retirer et anonymiser toutes les contributions d'un appareil",
    responses={
        200: {"description": "Retrait terminé ou déjà effectué"},
        429: {"model": ApiError, "description": "Quota dépassé"},
        500: {"model": ApiError, "description": "Erreur interne"},
        503: {"model": ApiError, "description": "Retrait incomplet, réessayer"},
    },
)
@limiter.limit(recognize_limit)
async def withdraw_recordings(
    request: Request,
    withdrawal: WithdrawalRequest,
    consent_repo: Annotated[ConsentRepo, Depends(get_consent_repo)],
    contribution_repo: Annotated[
        ContributionRepo,
        Depends(get_contribution_repo),
    ],
    store: Annotated[AudioStore, Depends(get_audio_store)],
) -> WithdrawalReceipt | JSONResponse:
    """Révoque, supprime puis anonymise sans exposer les ressources concernées."""

    request_id = request_id_from(request)
    service = WithdrawalService(
        consent_repo=consent_repo,
        contribution_repo=contribution_repo,
        audio_store=store,
    )
    try:
        await service.withdraw(withdrawal.anon_id)
        log.info(
            "withdrawal.completed",
            request_id=request_id,
            status="withdrawn",
        )
        return WithdrawalReceipt(status="withdrawn")
    except WithdrawalIncompleteError:
        return api_error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="WITHDRAWAL_INCOMPLETE",
            message="Withdrawal is incomplete; retry later",
            request_id=request_id,
            event="withdrawal.incomplete",
        )
    except Exception:
        return api_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL",
            message="Internal withdrawal error",
            request_id=request_id,
            event="withdrawal.incomplete",
        )


__all__ = [
    "RecordingReceipt",
    "WithdrawalReceipt",
    "WithdrawalRequest",
    "router",
]
