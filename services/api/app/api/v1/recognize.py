"""Endpoint POST /api/v1/recognize — pipeline complet via SpeechRecognizer."""

import asyncio
from time import perf_counter
from typing import Annotated, Literal
from uuid import UUID, uuid4

import zarma_numbers
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.asr.base import AsrResult, AudioInput, SpeechRecognizer
from app.asr.factory import get_recognizer
from app.config import Settings, get_settings
from app.core.consent import InvalidConsentError, require_valid_consent
from app.core.errors import ApiError, api_error_response, request_id_from
from app.core.rate_limit import limiter, recognize_limit
from app.db.repositories import (
    ConsentRepo,
    ContributionConsentInvalidError,
    ContributionCreate,
    ContributionRepo,
    RecognitionRepo,
    get_consent_repo,
    get_contribution_repo,
    get_recognition_repo,
)
from app.pipeline.audio import (
    MAX_AUDIO_SIZE,
    AudioValidationError,
    DecodedAudio,
    validate_and_decode,
)
from app.pipeline.recognition import run_recognition_pipeline
from app.storage.audio_store import AudioStorageError, AudioStore, get_audio_store

router = APIRouter(tags=["recognize"])

TIMEOUT_SECONDS = 30.0


class RecognizeRequest(BaseModel):
    """Champs de formulaire validés pour une requête de reconnaissance."""

    anon_id: UUID


class RecognitionAlternative(BaseModel):
    """Candidat alternatif retourné par le moteur ASR."""

    number: int | None
    zarma_text: str
    score: float = Field(ge=0.0, le=1.0)


class RecognizedExpression(BaseModel):
    """Opération reconnue et son résultat exact (story 6.1).

    Champ **additif** : il vaut ``None`` pour un énoncé « nombre seul », de sorte
    que le contrat des epics 1–5 est inchangé pour les clients existants.

    ``result`` porte le résultat entier (le quotient si ``remainder`` est non
    nul). Quand l'opération est comprise mais que sa réponse sort du domaine
    (résultat négatif, dépassement, division par zéro), ``result`` vaut ``None``
    et ``refusal_code`` dit pourquoi — jamais un résultat approché (FR21/NFR14).
    """

    left: int
    operator: Literal["+", "-", "*", "/"]
    right: int
    #: Forme zarma canonique de l'opération entendue (relisible à voix haute).
    zarma_text: str
    result: int | None = None
    #: Reste d'une division non entière ; ``0`` quand le résultat est exact.
    remainder: int = 0
    #: Forme zarma du résultat (``« waranka ga cindi hinza »`` = « 20 reste 3 »).
    result_zarma_text: str = ""
    refusal_code: str | None = None


class RecognitionResponse(BaseModel):
    """Réponse versionnée du pipeline de reconnaissance."""

    id: UUID
    recognized_number: int | None
    zarma_text: str
    normalized_text: str
    confidence: float = Field(ge=0.0, le=1.0)
    decision: Literal["accept", "confirm", "repeat"]
    alternatives: list[RecognitionAlternative] = Field(default_factory=list)
    #: Présent uniquement si l'énoncé était une opération (story 6.1).
    expression: RecognizedExpression | None = None
    model_version: str
    grammar_version: str
    latency_total_ms: int = Field(ge=0)
    latency_asr_ms: int = Field(ge=0)

    model_config = {"protected_namespaces": (), "from_attributes": True}


def _alternative_from(text: str, score: float) -> RecognitionAlternative:
    """Alternative ASR résolue en nombre **ou** en opération (story 6.1).

    Un nombre reste rendu comme avant. Une alternative qui est une opération
    porte la valeur de son résultat et la forme canonique de l'opération, de
    sorte que l'écran de confirmation présente quelque chose de comparable
    plutôt qu'une transcription brute. Une opération hors domaine n'a pas de
    valeur : elle garde son texte, sans nombre inventé (FR21).
    """
    number = zarma_numbers.parse(text)
    if number is not None:
        return RecognitionAlternative(
            number=number, zarma_text=zarma_numbers.generate(number), score=score
        )

    expression = zarma_numbers.parse_expression(text)
    if expression is not None:
        zarma_text = zarma_numbers.render_expression(expression)
        try:
            value = zarma_numbers.evaluate(expression).value
        except zarma_numbers.DomainError:
            value = None
        return RecognitionAlternative(number=value, zarma_text=zarma_text, score=score)

    return RecognitionAlternative(number=None, zarma_text=text, score=score)


async def _run_pipeline(
    *,
    audio: DecodedAudio,
    recognizer: SpeechRecognizer,
    repo: RecognitionRepo,
    anon_id: UUID,
    settings: Settings,
    request_start: float,
) -> RecognitionResponse:
    asr_result: AsrResult = await asyncio.to_thread(
        recognizer.transcribe,
        AudioInput(data=audio.pcm, format="pcm_s16le"),
    )
    outcome = run_recognition_pipeline(asr_result, settings)

    expression = None
    if outcome.expression is not None:
        result = outcome.expression_result
        expression = RecognizedExpression(
            left=outcome.expression.left,
            operator=outcome.expression.symbol,
            right=outcome.expression.right,
            zarma_text=outcome.zarma_text,
            result=result.value if result is not None else None,
            remainder=result.remainder if result is not None else 0,
            result_zarma_text=outcome.result_zarma_text,
            refusal_code=outcome.refusal_code,
        )

    sorted_candidates = sorted(
        asr_result.candidates,
        key=lambda candidate: candidate.score,
        reverse=True,
    )
    alternatives = [
        _alternative_from(candidate.text, candidate.score) for candidate in sorted_candidates
    ]
    latency_total_ms = max(
        int((perf_counter() - request_start) * 1000),
        asr_result.latency_ms,
    )

    response = RecognitionResponse(
        id=uuid4(),
        recognized_number=outcome.number,
        zarma_text=outcome.zarma_text,
        normalized_text=outcome.normalized_text,
        confidence=outcome.confidence.score,
        decision=outcome.decision,
        alternatives=alternatives,
        expression=expression,
        model_version=asr_result.model_version,
        grammar_version=zarma_numbers.load_lexicon().grammar_version,
        latency_total_ms=latency_total_ms,
        latency_asr_ms=asr_result.latency_ms,
    )
    await repo.save(response, anon_id, asr_result.text)
    return response


@router.post(
    "/recognize",
    response_model=RecognitionResponse,
    summary="Reconnaissance vocale complète",
    responses={
        200: {"description": "Recognition successful"},
        400: {"model": ApiError, "description": "Invalid audio"},
        413: {"model": ApiError, "description": "File too large"},
        422: {"model": ApiError, "description": "Invalid input"},
        500: {"model": ApiError, "description": "Internal server error"},
        504: {"model": ApiError, "description": "Recognition timeout"},
    },
)
@limiter.limit(recognize_limit)
async def recognize(
    request: Request,
    audio: Annotated[
        UploadFile,
        File(description=f"WAV audio, maximum {MAX_AUDIO_SIZE // 1_000_000} MB"),
    ],
    anon_id: Annotated[UUID, Form(description="Anonymous device UUID")],
    recognizer: Annotated[SpeechRecognizer, Depends(get_recognizer)],
    repo: Annotated[RecognitionRepo, Depends(get_recognition_repo)],
    consent_repo: Annotated[ConsentRepo, Depends(get_consent_repo)],
    contribution_repo: Annotated[
        ContributionRepo,
        Depends(get_contribution_repo),
    ],
    store: Annotated[AudioStore, Depends(get_audio_store)],
    settings: Annotated[Settings, Depends(get_settings)],
    consent_id: Annotated[
        UUID | None,
        Form(description="Current consent UUID"),
    ] = None,
) -> RecognitionResponse | JSONResponse:
    """Valide puis exécute ASR → normalisation → parsing sous timeout."""

    request_start = perf_counter()
    request_id = request_id_from(request)
    _request = RecognizeRequest(anon_id=anon_id)

    audio_ref: str | None = None
    try:
        async with asyncio.timeout(TIMEOUT_SECONDS):
            if settings.REQUIRE_TRAINING_CONSENT:
                if consent_id is None:
                    raise InvalidConsentError
                await require_valid_consent(
                    repo=consent_repo,
                    consent_id=consent_id,
                    anon_id=anon_id,
                )
            decoded_audio = await validate_and_decode(audio)
            if consent_id is not None:
                audio_ref = await store.save(decoded_audio)
            response = await _run_pipeline(
                audio=decoded_audio,
                recognizer=recognizer,
                repo=repo,
                anon_id=anon_id,
                settings=settings,
                request_start=request_start,
            )
            if consent_id is None or audio_ref is None:
                return response
            expression_result = (
                response.expression.result if response.expression is not None else None
            )
            expected_number = (
                response.recognized_number
                if response.recognized_number is not None
                else expression_result or 0
            )
            expected_prompt = (
                response.normalized_text.strip() or response.zarma_text.strip() or "[à revoir]"
            )
            await contribution_repo.save(
                ContributionCreate(
                    anon_id=anon_id,
                    consent_id=consent_id,
                    expected_number=expected_number,
                    expected_prompt=expected_prompt,
                    audio_ref=audio_ref,
                    region=None,
                    device_info=None,
                    model_version=response.model_version,
                    grammar_version=response.grammar_version,
                    recognition_id=response.id,
                    source="calculation",
                )
            )
            audio_ref = None
            return response
    except (InvalidConsentError, ContributionConsentInvalidError):
        return api_error_response(
            status_code=status.HTTP_403_FORBIDDEN,
            code="CONSENT_INVALID",
            message="Valid consent required",
            request_id=request_id,
        )
    except AudioValidationError as exc:
        return api_error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            request_id=request_id,
        )
    except TimeoutError:
        return api_error_response(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            code="TIMEOUT",
            message="Recognition processing timed out",
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
        return api_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL",
            message="Internal recognition error",
            request_id=request_id,
        )
    finally:
        if audio_ref is not None:
            try:
                await store.delete(audio_ref)
            except AudioStorageError:
                pass
        await audio.close()
