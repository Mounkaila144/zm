"""Configuration centralisée du service API (pydantic-settings).

Règle de standard : **toute** lecture de configuration passe par l'objet
``Settings`` — jamais d'accès ``os.environ`` dispersé — et **aucun secret n'est
en dur**. Les valeurs proviennent des variables d'environnement (et d'un
``.env`` hors Git), avec des valeurs par défaut sûres pour le développement.

Note : ``GRAMMAR_VERSION`` est une valeur *informative* de config ; la source
de vérité de la version de grammaire est le lexique (``zarma_numbers``), exposée
par l'endpoint ``/api/v1/grammar/version``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Modes de reconnaissance ASR connus (implémentations réelles en stories 2.2+).
AsrMode = Literal["mock", "ctc", "llm"]


class Settings(BaseSettings):
    """Paramètres du service, lus depuis l'environnement / ``.env``.

    Les noms de champs correspondent aux variables d'environnement
    (correspondance insensible à la casse assurée par pydantic-settings).
    """

    APP_ENV: Literal["development", "staging", "production"] = "development"
    DATABASE_URL: str = "sqlite+aiosqlite:///./zarma.db"
    ASR_MODE: AsrMode = "mock"
    # Endpoint ASR distant (Modal) — requis seulement en mode ``ctc``/``llm``.
    ASR_ENDPOINT_URL: str = ""
    # Secret d'accès à l'endpoint ASR — jamais en dur, jamais côté mobile (NFR3).
    ASR_ENDPOINT_TOKEN: str = ""
    # Timeout d'un appel ASR distant (cold start compris) avant repli ``repeat``.
    ASR_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0.0)
    # Transcription forcée du MockRecognizer — **développement/démo uniquement**.
    # Vide (défaut) = comportement historique : le mock ne transcrit rien, donc
    # le pipeline conclut ``repeat``. Renseignée, elle permet d'exercer le flux
    # complet sur un appareil sans GPU ni endpoint ASR. Sans effet dès que
    # ``ASR_MODE`` vaut ``ctc`` ou ``llm`` : aucun risque de fuite en production.
    ASR_MOCK_TEXT: str = ""
    # Informatif uniquement — la vérité vient du lexique (voir /grammar/version).
    GRAMMAR_VERSION: str = "1.0.0"
    LOG_LEVEL: str = "INFO"
    RATE_LIMIT_RECOGNIZE: str = "10/minute"
    AUDIO_STORAGE_DIR: Path = Path("./storage/audio")

    # Défauts prudents du score composite ; calibration réelle en Epic 5 / story 5.5.
    CONF_WEIGHT_ACOUSTIC: float = Field(default=0.35, ge=0.0)
    CONF_WEIGHT_GRAMMAR: float = Field(default=0.30, ge=0.0)
    CONF_WEIGHT_VARIANT: float = Field(default=0.10, ge=0.0)
    CONF_WEIGHT_MARGIN: float = Field(default=0.15, ge=0.0)
    CONF_WEIGHT_CONFUSION: float = Field(default=0.10, ge=0.0)
    POLICY_ACCEPT_THRESHOLD: float = Field(default=0.80, ge=0.0, le=1.0)
    POLICY_CONFIRM_THRESHOLD: float = Field(default=0.50, ge=0.0, le=1.0)
    POLICY_MARGIN_THRESHOLD: float = Field(default=0.15, ge=0.0, le=1.0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_confidence_configuration(self) -> Self:
        """Refuse les poids inutilisables et des seuils non monotones."""

        weight_sum = (
            self.CONF_WEIGHT_ACOUSTIC
            + self.CONF_WEIGHT_GRAMMAR
            + self.CONF_WEIGHT_VARIANT
            + self.CONF_WEIGHT_MARGIN
            + self.CONF_WEIGHT_CONFUSION
        )
        if weight_sum <= 0:
            raise ValueError("At least one confidence weight must be positive")
        if self.POLICY_CONFIRM_THRESHOLD > self.POLICY_ACCEPT_THRESHOLD:
            raise ValueError("POLICY_CONFIRM_THRESHOLD must not exceed POLICY_ACCEPT_THRESHOLD")
        if self.ASR_MODE in ("ctc", "llm") and not self.ASR_ENDPOINT_URL:
            raise ValueError("ASR_ENDPOINT_URL is required when ASR_MODE is 'ctc' or 'llm'")
        return self


@lru_cache
def get_settings() -> Settings:
    """Retourne l'instance ``Settings`` mise en cache (source unique de config)."""
    return Settings()
