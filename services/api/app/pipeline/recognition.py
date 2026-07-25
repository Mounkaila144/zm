"""Cœur **pur** du pipeline de reconnaissance (ASR → nombre → décision).

Cette fonction est **sans I/O, sans persistance, sans FastAPI** : à partir d'un
``AsrResult`` déjà obtenu et des ``Settings`` effectifs, elle rejoue l'exact
enchaînement de décision de ``/api/v1/recognize`` — normalisation, parsing,
candidats numériques, confiance composite, politique accept/confirm/repeat.

Elle est la **source unique** de cet enchaînement : la route API *et* le harnais
de benchmark (Epic 5) l'appellent, de sorte qu'aucune règle de décision n'est
dupliquée (isolation du moteur linguistique).
"""

from __future__ import annotations

from dataclasses import dataclass

import zarma_numbers

from app.asr.base import AsrResult
from app.config import Settings
from app.pipeline.confidence import (
    ConfidenceResult,
    NumericCandidate,
    composite_confidence,
    numeric_candidates_from_asr,
)
from app.pipeline.policy import Decision, decide


@dataclass(frozen=True, slots=True)
class RecognitionOutcome:
    """Résultat déterministe du cœur de décision (aucune donnée d'I/O)."""

    normalized_text: str
    number: int | None
    zarma_text: str
    numeric_candidates: list[NumericCandidate]
    confidence: ConfidenceResult
    decision: Decision


def run_recognition_pipeline(asr_result: AsrResult, settings: Settings) -> RecognitionOutcome:
    """Exécute normalisation → parsing → confiance → politique sur un ``AsrResult``.

    Aucun nombre n'est inventé : un texte non numérique reste ``number is None``
    et conduit à ``repeat`` (FR21). Comportement identique à la route.
    """

    normalized_text = zarma_numbers.normalize(asr_result.text)
    number = zarma_numbers.parse(normalized_text)
    numeric_candidates = numeric_candidates_from_asr(asr_result)
    confidence = composite_confidence(
        asr=asr_result,
        normalized_text=normalized_text,
        number=number,
        numeric_candidates=numeric_candidates,
        settings=settings,
    )
    decision = decide(
        score=confidence.score,
        number=number,
        numeric_candidates=numeric_candidates,
        settings=settings,
    )
    zarma_text = zarma_numbers.generate(number) if number is not None else ""

    return RecognitionOutcome(
        normalized_text=normalized_text,
        number=number,
        zarma_text=zarma_text,
        numeric_candidates=numeric_candidates,
        confidence=confidence,
        decision=decision,
    )


__all__ = ["RecognitionOutcome", "run_recognition_pipeline"]
