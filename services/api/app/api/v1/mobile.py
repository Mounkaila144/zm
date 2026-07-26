"""Politique de compatibilité de l'application mobile."""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel
from starlette.responses import Response

from app.config import Settings, get_settings
from app.core.errors import api_error_response, request_id_from

router = APIRouter(tags=["mobile"])


class MobileConfigResponse(BaseModel):
    minimum_supported_build: int
    latest_build: int
    play_store_url: str


@router.get(
    "/mobile/config",
    response_model=MobileConfigResponse,
    summary="Version minimale autorisée de l'application mobile",
)
async def mobile_config(
    settings: Annotated[Settings, Depends(get_settings)],
) -> MobileConfigResponse:
    return MobileConfigResponse(
        minimum_supported_build=settings.MOBILE_MIN_SUPPORTED_BUILD,
        latest_build=settings.MOBILE_LATEST_BUILD,
        play_store_url=settings.MOBILE_PLAY_STORE_URL,
    )


async def mobile_version_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Bloque les anciens builds avant même la validation du formulaire."""

    settings = get_settings()
    if settings.MOBILE_ENFORCE_MIN_BUILD and request.url.path == "/api/v1/recognize":
        raw_build = request.headers.get("X-App-Build", "0")
        try:
            app_build = int(raw_build)
        except ValueError:
            app_build = 0
        if app_build < settings.MOBILE_MIN_SUPPORTED_BUILD:
            return api_error_response(
                status_code=status.HTTP_426_UPGRADE_REQUIRED,
                code="APP_UPDATE_REQUIRED",
                message="A newer application version is required",
                request_id=request_id_from(request),
            )
    return await call_next(request)


__all__ = [
    "MobileConfigResponse",
    "mobile_config",
    "mobile_version_middleware",
    "router",
]
