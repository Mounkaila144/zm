"""Point d'entrée de l'application FastAPI Zarma.

Assemble l'app (titre / version / description), monte les routers versionnés
``/api/v1`` et la sonde ``/health``. La documentation OpenAPI est générée
nativement (``/docs``, ``/openapi.json``) — pattern contract-first.

Démarrage local :
    uv run uvicorn app.main:app --app-dir services/api --reload
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.exceptions import HTTPException

from app import __version__
from app.api.v1 import (
    consent,
    feedback,
    grammar,
    health,
    history,
    metrics,
    mobile,
    models,
    recognize,
    recordings,
)
from app.asr import grammar_guard
from app.config import get_settings
from app.core.errors import (
    http_exception_handler,
    rate_limit_handler,
    request_id_middleware,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging
from app.core.rate_limit import limiter
from app.db.models import Base
from app.db.session import engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Crée le schéma en développement ; staging/prod utilisent Alembic."""

    settings = get_settings()
    if settings.APP_ENV == "development":
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    # Vérifie au démarrage que le service ASR et l'API partagent la même
    # grammaire. Ne bloque jamais le démarrage (cf. ``grammar_guard.probe``).
    await grammar_guard.probe(settings)
    yield


def create_app() -> FastAPI:
    """Construit et configure l'instance FastAPI (factory testable)."""
    configure_logging(get_settings().LOG_LEVEL)
    app = FastAPI(
        title="Zarma API",
        version=__version__,
        description=(
            "Service API du système Zarma : santé, traçabilité des versions "
            "(grammaire, recognizers) et, à venir, reconnaissance des nombres."
        ),
        lifespan=lifespan,
    )
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.middleware("http")(request_id_middleware)
    app.middleware("http")(mobile.mobile_version_middleware)
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # Sonde de santé à la racine (hors versionnement).
    app.include_router(health.router)

    # Endpoints métier versionnés sous /api/v1.
    v1 = APIRouter(prefix="/api/v1")
    v1.include_router(models.router)
    v1.include_router(mobile.router)
    v1.include_router(grammar.router)
    v1.include_router(recognize.router)
    v1.include_router(history.router)
    v1.include_router(feedback.router)
    v1.include_router(metrics.router)
    v1.include_router(consent.router)
    v1.include_router(recordings.router)
    app.include_router(v1)

    return app


app = create_app()
