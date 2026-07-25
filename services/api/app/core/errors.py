"""Gestion centralisée des erreurs publiques, sans fuite de détails internes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException
from starlette.responses import Response
from structlog import get_logger

RequestHandler = Callable[[Request], Awaitable[Response]]
log = get_logger("zarma.api")


class ErrorResponse(BaseModel):
    """Détail sûr et corrélable d'une erreur API."""

    code: str
    message: str
    request_id: str
    timestamp: str


class ApiError(BaseModel):
    """Enveloppe commune de toutes les erreurs publiques."""

    error: ErrorResponse


def request_id_from(request: Request) -> str:
    """Lit l'identifiant de corrélation, avec repli sûr hors middleware."""

    return getattr(request.state, "request_id", str(uuid4()))


async def request_id_middleware(
    request: Request,
    call_next: RequestHandler,
) -> Response:
    """Associe à chaque requête un UUID anonyme renvoyé au client."""

    request.state.request_id = str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


def api_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str | None = None,
    event: str | None = None,
) -> JSONResponse:
    """Construit l'unique forme de réponse d'erreur exposée par l'API."""

    resolved_request_id = request_id or str(uuid4())
    timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    payload = ApiError(
        error=ErrorResponse(
            code=code,
            message=message,
            request_id=resolved_request_id,
            timestamp=timestamp,
        )
    )
    log_method = log.error if status_code >= 500 else log.warning
    log_method(
        event or ("unhandled" if status_code >= 500 else "request_failed"),
        request_id=resolved_request_id,
        error_code=code,
        status_code=status_code,
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(),
        headers={"X-Request-ID": resolved_request_id},
    )


def _safe_http_error(status_code: int) -> tuple[str, str]:
    """Mappe un statut HTTP vers un code et message publics prédéfinis."""

    mapping = {
        status.HTTP_400_BAD_REQUEST: ("BAD_REQUEST", "Bad request"),
        status.HTTP_401_UNAUTHORIZED: ("UNAUTHORIZED", "Unauthorized"),
        status.HTTP_403_FORBIDDEN: ("FORBIDDEN", "Forbidden"),
        status.HTTP_404_NOT_FOUND: ("NOT_FOUND", "Resource not found"),
        status.HTTP_405_METHOD_NOT_ALLOWED: (
            "METHOD_NOT_ALLOWED",
            "Method not allowed",
        ),
        status.HTTP_409_CONFLICT: ("CONFLICT", "Conflict"),
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: (
            "PAYLOAD_TOO_LARGE",
            "Request payload too large",
        ),
        status.HTTP_422_UNPROCESSABLE_ENTITY: (
            "VALIDATION_ERROR",
            "Request validation failed",
        ),
        status.HTTP_429_TOO_MANY_REQUESTS: (
            "RATE_LIMITED",
            "Too many requests",
        ),
        status.HTTP_503_SERVICE_UNAVAILABLE: (
            "SERVICE_UNAVAILABLE",
            "Service unavailable",
        ),
        status.HTTP_504_GATEWAY_TIMEOUT: ("TIMEOUT", "Request timed out"),
    }
    return mapping.get(status_code, ("HTTP_ERROR", "Request failed"))


async def validation_exception_handler(
    request: Request,
    _exc: RequestValidationError,
) -> JSONResponse:
    """Normalise une erreur de validation sans refléter l'entrée reçue."""

    return api_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="VALIDATION_ERROR",
        message="Request validation failed",
        request_id=request_id_from(request),
    )


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """Normalise une erreur HTTP sans exposer son détail potentiellement interne."""

    code, message = _safe_http_error(exc.status_code)
    return api_error_response(
        status_code=exc.status_code,
        code=code,
        message=message,
        request_id=request_id_from(request),
    )


async def rate_limit_handler(
    request: Request,
    _exc: RateLimitExceeded,
) -> JSONResponse:
    """Traduit la réponse slowapi brute vers le contrat d'erreur public."""

    return api_error_response(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        code="RATE_LIMITED",
        message="Too many requests",
        request_id=request_id_from(request),
    )


async def unhandled_exception_handler(
    request: Request,
    _exc: Exception,
) -> JSONResponse:
    """Masque toute exception inattendue derrière un message générique."""

    return api_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="INTERNAL",
        message="Internal server error",
        request_id=request_id_from(request),
    )


__all__ = [
    "ApiError",
    "ErrorResponse",
    "api_error_response",
    "http_exception_handler",
    "rate_limit_handler",
    "request_id_from",
    "request_id_middleware",
    "unhandled_exception_handler",
    "validation_exception_handler",
]
