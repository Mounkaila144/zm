"""Politique prudente accept/confirm/repeat, décidée côté serveur."""

from __future__ import annotations

from typing import Literal

from app.config import Settings
from app.pipeline.confidence import NumericCandidate

Decision = Literal["accept", "confirm", "repeat"]


def decide(
    *,
    score: float,
    number: int | None,
    numeric_candidates: list[NumericCandidate],
    settings: Settings,
) -> Decision:
    """Applique l'ordre de décision FR13/FR15/FR21 sans inventer de nombre."""

    if number is None:
        return "repeat"
    if (
        len(numeric_candidates) >= 2
        and numeric_candidates[0].score - numeric_candidates[1].score
        < settings.POLICY_MARGIN_THRESHOLD
    ):
        return "confirm"
    if score >= settings.POLICY_ACCEPT_THRESHOLD:
        return "accept"
    if score >= settings.POLICY_CONFIRM_THRESHOLD:
        return "confirm"
    return "repeat"


__all__ = ["Decision", "decide"]
