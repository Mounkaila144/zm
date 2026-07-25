"""Validation serveur réutilisable du consentement spécifique à un upload."""

from __future__ import annotations

from uuid import UUID

from app.db.models import Consent
from app.db.repositories import ConsentRepo


class InvalidConsentError(Exception):
    """Consentement absent, non possédé, obsolète ou retiré."""


async def require_valid_consent(
    *,
    repo: ConsentRepo,
    consent_id: UUID,
    anon_id: UUID,
) -> Consent:
    """Valide sans distinguer publiquement les causes de refus."""

    consent = await repo.valid_for(consent_id, anon_id)
    if consent is None:
        raise InvalidConsentError
    return consent


__all__ = ["InvalidConsentError", "require_valid_consent"]
