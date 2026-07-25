"""Factory for ASR implementation selection via configuration.

This module implements the Strategy/Adapter pattern for ASR implementations,
allowing runtime selection of the recognition engine based on ASR_MODE setting.
"""

from typing import Annotated

from fastapi import Depends

from app.asr.base import SpeechRecognizer
from app.asr.mock import MockRecognizer
from app.asr.remote import RemoteCtcRecognizer, RemoteLlmRecognizer
from app.config import Settings, get_settings


def get_recognizer(
    settings: Annotated[Settings, Depends(get_settings)],
) -> SpeechRecognizer:
    """Factory: selects ASR implementation based on settings.ASR_MODE.

    Le passage Mock ↔ modèle réel se fait **uniquement** par configuration
    (``ASR_MODE`` + ``ASR_ENDPOINT_URL``/token) — aucun changement d'API ni de
    mobile (NFR9).

    Args:
        settings: Application settings containing ASR_MODE configuration

    Returns:
        SpeechRecognizer implementation based on ASR_MODE

    Raises:
        ValueError: If ASR_MODE is not supported
    """
    if settings.ASR_MODE == "mock":
        recognizer = MockRecognizer()
        if settings.ASR_MOCK_TEXT:
            # Confort de développement : exercer le pipeline complet sur un
            # appareil réel, sans GPU ni endpoint. Ne s'applique qu'au mock.
            recognizer.set_text(settings.ASR_MOCK_TEXT)
        return recognizer
    if settings.ASR_MODE == "ctc":
        return RemoteCtcRecognizer(settings)
    if settings.ASR_MODE == "llm":
        return RemoteLlmRecognizer(settings)
    raise ValueError(f"ASR_MODE {settings.ASR_MODE} not supported (expected mock|ctc|llm)")
