"""Imports de compatibilité pour l'ancien emplacement des erreurs API."""

from app.core.errors import ApiError, ErrorResponse, api_error_response

__all__ = [
    "ApiError",
    "ErrorResponse",
    "api_error_response",
]
