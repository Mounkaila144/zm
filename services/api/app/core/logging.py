"""Configuration des logs JSON sans PII pour l'API."""

from __future__ import annotations

import logging

import structlog


def configure_logging(level: str) -> None:
    """Configure structlog au niveau demandé par les settings."""

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=numeric_level, format="%(message)s")
    logging.getLogger("zarma.api").setLevel(numeric_level)

    # slowapi journalise sinon la clé de quota (potentiellement une IP).
    logging.getLogger("slowapi").setLevel(logging.ERROR)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )


__all__ = ["configure_logging"]
