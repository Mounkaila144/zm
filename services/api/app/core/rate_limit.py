"""Rate limiting anonyme et configurable pour les endpoints sensibles."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.config import get_settings


def anonymous_key(request: Request) -> str:
    """Identifie anonymement un client sans persister ni journaliser de PII."""

    anon_id = request.query_params.get("anon_id")
    return anon_id or get_remote_address(request)


def recognize_limit() -> str:
    """Retourne la limite courante depuis la configuration centralisée."""

    return get_settings().RATE_LIMIT_RECOGNIZE


limiter = Limiter(key_func=anonymous_key)

__all__ = ["anonymous_key", "limiter", "recognize_limit"]
