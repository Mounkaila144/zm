"""Cœur **pur** du pipeline de reconnaissance (ASR → nombre → décision).

Cette fonction est **sans I/O, sans persistance, sans FastAPI** : à partir d'un
``AsrResult`` déjà obtenu et des ``Settings`` effectifs, elle rejoue l'exact
enchaînement de décision de ``/api/v1/recognize`` — normalisation, parsing,
candidats numériques, confiance composite, politique accept/confirm/repeat.

Elle est la **source unique** de cet enchaînement : la route API *et* le harnais
de benchmark (Epic 5) l'appellent, de sorte qu'aucune règle de décision n'est
dupliquée (isolation du moteur linguistique).

Story 6.1 — un énoncé peut aussi être une **opération**. L'extension est
volontairement additive :

- on tente d'abord un **nombre seul**, exactement comme avant ;
- ce n'est que si aucun nombre n'est reconnu qu'on tente une **expression**.
  Les deux langues sont disjointes (aucun mot d'opérateur n'appartient à un
  nombre, cf. ``build_expression_grammar``), donc cet ordre n'introduit aucune
  ambiguïté : un texte ne peut pas être les deux.

Conséquence recherchée : le chemin « nombre seul » des epics 1–5 est
**inchangé**, jusque dans les valeurs de confiance et la décision.
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
    expression_candidates_from_asr,
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
    #: Opération reconnue, si l'énoncé en était une (story 6.1).
    expression: zarma_numbers.Expression | None = None
    #: Résultat exact de cette opération, ``None`` si elle sort du domaine.
    expression_result: zarma_numbers.ExpressionResult | None = None
    #: Forme zarma du résultat (``« … ga cindi … »`` pour une division à reste).
    result_zarma_text: str = ""
    #: Code de refus arithmétique (``NEGATIVE_RESULT``…) — jamais un résultat approché.
    refusal_code: str | None = None


def _recognize_expression(
    normalized_text: str,
) -> tuple[zarma_numbers.Expression | None, zarma_numbers.ExpressionResult | None, str | None]:
    """Analyse et évalue une expression. Refus explicite plutôt que résultat inventé."""
    expression = zarma_numbers.parse_expression(normalized_text)
    if expression is None:
        return None, None, None
    try:
        return expression, zarma_numbers.evaluate(expression), None
    except zarma_numbers.DomainError as exc:
        # L'énoncé est compris, mais la réponse n'existe pas dans le domaine :
        # ce n'est PAS un échec de reconnaissance (FR21). L'utilisateur doit
        # l'apprendre, pas se voir demander de répéter.
        return expression, None, exc.code


def run_recognition_pipeline(asr_result: AsrResult, settings: Settings) -> RecognitionOutcome:
    """Exécute normalisation → parsing → confiance → politique sur un ``AsrResult``.

    Aucun nombre n'est inventé : un texte ni numérique ni arithmétique reste
    ``number is None`` et conduit à ``repeat`` (FR21). Comportement identique à
    la route.
    """

    normalized_text = zarma_numbers.normalize(asr_result.text)
    number = zarma_numbers.parse(normalized_text)

    expression = expression_result = refusal_code = None
    if number is None:
        expression, expression_result, refusal_code = _recognize_expression(normalized_text)

    expression_recognized = expression is not None
    numeric_candidates = (
        expression_candidates_from_asr(asr_result)
        if expression_recognized
        else numeric_candidates_from_asr(asr_result)
    )
    confidence = composite_confidence(
        asr=asr_result,
        normalized_text=normalized_text,
        number=number,
        numeric_candidates=numeric_candidates,
        settings=settings,
        expression_recognized=expression_recognized,
    )
    decision = decide(
        score=confidence.score,
        number=number,
        numeric_candidates=numeric_candidates,
        settings=settings,
        expression_recognized=expression_recognized,
    )
    zarma_text = zarma_numbers.generate(number) if number is not None else ""
    if expression is not None:
        zarma_text = zarma_numbers.render_expression(expression)
    result_zarma_text = (
        zarma_numbers.render_result(expression_result) if expression_result is not None else ""
    )

    return RecognitionOutcome(
        normalized_text=normalized_text,
        number=number,
        zarma_text=zarma_text,
        numeric_candidates=numeric_candidates,
        confidence=confidence,
        decision=decision,
        expression=expression,
        expression_result=expression_result,
        result_zarma_text=result_zarma_text,
        refusal_code=refusal_code,
    )


__all__ = ["RecognitionOutcome", "run_recognition_pipeline"]
