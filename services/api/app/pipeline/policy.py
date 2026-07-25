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
    expression_recognized: bool = False,
) -> Decision:
    """Applique l'ordre de décision FR13/FR15/FR21 sans inventer de nombre.

    ``expression_recognized`` (story 6.1) traite une **expression** reconnue
    comme un énoncé compris : la politique elle-même est inchangée — c'est la
    même échelle accept/confirm/repeat, appliquée à un énoncé d'une autre forme.
    Par défaut ``False`` : le comportement « nombre seul » ne bouge pas.
    """

    if number is None and not expression_recognized:
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
