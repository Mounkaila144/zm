"""Calcul traçable de la confiance composite de reconnaissance."""

from __future__ import annotations

from dataclasses import dataclass

import zarma_numbers

from app.asr.base import AsrResult
from app.config import Settings


@dataclass(frozen=True, slots=True)
class NumericCandidate:
    """Candidat ASR dont le texte est parsable comme nombre zarma."""

    number: int
    text: str
    score: float


@dataclass(frozen=True, slots=True)
class ConfidenceResult:
    """Score final et détail borné des cinq signaux FR12."""

    score: float
    acoustic: float
    grammatical: float
    variant: float
    margin: float
    confusion: float


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def numeric_candidates_from_asr(asr: AsrResult) -> list[NumericCandidate]:
    """Parse et classe le résultat principal et ses alternatives sans fuzzy matching."""

    transcriptions = [(asr.text, asr.acoustic_score)]
    transcriptions.extend((candidate.text, candidate.score) for candidate in asr.candidates)

    by_number: dict[int, NumericCandidate] = {}
    for text, score in transcriptions:
        normalized = zarma_numbers.normalize(text)
        number = zarma_numbers.parse(normalized)
        if number is None:
            continue
        candidate = NumericCandidate(number=number, text=normalized, score=_clamp(score))
        previous = by_number.get(number)
        if previous is None or candidate.score > previous.score:
            by_number[number] = candidate

    return sorted(by_number.values(), key=lambda candidate: candidate.score, reverse=True)


def expression_candidates_from_asr(asr: AsrResult) -> list[NumericCandidate]:
    """Idem, pour les transcriptions qui sont des **expressions** (story 6.1).

    Chaque candidat est indexé par la valeur de son résultat : c'est elle qui
    porte le désaccord entre hypothèses, donc le signal de marge. Les
    expressions dont le résultat sort du domaine sont écartées — un refus n'est
    pas un candidat.

    Fonction **distincte** de ``numeric_candidates_from_asr`` : le chemin
    « nombre seul » des epics 1–5 ne passe jamais ici et reste inchangé.
    """

    transcriptions = [(asr.text, asr.acoustic_score)]
    transcriptions.extend((candidate.text, candidate.score) for candidate in asr.candidates)

    by_value: dict[int, NumericCandidate] = {}
    for text, score in transcriptions:
        normalized = zarma_numbers.normalize(text)
        expression = zarma_numbers.parse_expression(normalized)
        if expression is None:
            continue
        try:
            result = zarma_numbers.evaluate(expression)
        except zarma_numbers.DomainError:
            continue
        candidate = NumericCandidate(number=result.value, text=normalized, score=_clamp(score))
        previous = by_value.get(result.value)
        if previous is None or candidate.score > previous.score:
            by_value[result.value] = candidate

    return sorted(by_value.values(), key=lambda candidate: candidate.score, reverse=True)


def _variant_signal(text: str) -> float:
    trace = zarma_numbers.normalize_with_trace(text)
    tokens = trace.normalized.split()
    if not tokens:
        return 0.0

    lexicon = zarma_numbers.load_lexicon()
    variants = lexicon.linguistic_variant_map()
    known_tokens = set(variants) | set(variants.values())
    return sum(token in known_tokens for token in tokens) / len(tokens)


def _margin_signal(candidates: list[NumericCandidate]) -> float:
    if not candidates:
        return 0.0
    if len(candidates) == 1:
        return 1.0
    return _clamp(candidates[0].score - candidates[1].score)


def is_known_asr_confusion(left: str, right: str, confusions: dict[str, str]) -> bool:
    """Vrai si deux formes diffèrent d'un seul token, lié par ``asr_confusions``.

    Réutilise **exactement** la logique du signal de confusion (aucun fuzzy
    matching, NFR14) : normalise, exige une unique différence de token, et vérifie
    que ce couple appartient à la table de corrections d'erreurs ASR — jamais à la
    table de variantes linguistiques (FR8). Exposée publiquement pour la matrice de
    confusions du harnais de benchmark (story 5.2).
    """

    left_tokens = zarma_numbers.normalize_with_trace(left).normalized.split()
    right_tokens = zarma_numbers.normalize_with_trace(right).normalized.split()
    if len(left_tokens) != len(right_tokens):
        return False

    differences = [
        (left_token, right_token)
        for left_token, right_token in zip(left_tokens, right_tokens, strict=True)
        if left_token != right_token
    ]
    if len(differences) != 1:
        return False

    left_token, right_token = differences[0]
    return confusions.get(left_token) == right_token or confusions.get(right_token) == left_token


#: Alias interne rétro-compatible (comportement identique).
_is_known_confusion = is_known_asr_confusion


def _confusion_signal(asr: AsrResult) -> float:
    ranked = [(asr.text, asr.acoustic_score)]
    ranked.extend((candidate.text, candidate.score) for candidate in asr.candidates)
    ranked.sort(key=lambda item: item[1], reverse=True)
    if len(ranked) < 2:
        return 1.0

    best_text = ranked[0][0]
    confusions = zarma_numbers.load_lexicon().asr_confusions
    return (
        0.0
        if any(
            _is_known_confusion(best_text, competitor_text, confusions)
            for competitor_text, _score in ranked[1:]
        )
        else 1.0
    )


def composite_confidence(
    *,
    asr: AsrResult,
    normalized_text: str,
    number: int | None,
    numeric_candidates: list[NumericCandidate],
    settings: Settings,
    expression_recognized: bool = False,
) -> ConfidenceResult:
    """Combine les cinq signaux configurables en une moyenne pondérée normalisée.

    ``expression_recognized`` (story 6.1) signale qu'une **expression** valide a
    été reconnue là où aucun nombre seul ne l'a été : le signal grammatical vaut
    alors 1, comme pour un nombre. Par défaut ``False``, de sorte que le chemin
    des epics 1–5 est strictement inchangé.
    """

    parsed = zarma_numbers.parse_detailed(normalized_text)
    grammatical = (number is not None and parsed.accepted) or expression_recognized
    signals = {
        "acoustic": _clamp(
            max([asr.acoustic_score, *(candidate.score for candidate in asr.candidates)])
        ),
        "grammatical": 1.0 if grammatical else 0.0,
        "variant": _clamp(_variant_signal(asr.text)),
        "margin": _margin_signal(numeric_candidates),
        "confusion": _confusion_signal(asr),
    }
    weights = {
        "acoustic": settings.CONF_WEIGHT_ACOUSTIC,
        "grammatical": settings.CONF_WEIGHT_GRAMMAR,
        "variant": settings.CONF_WEIGHT_VARIANT,
        "margin": settings.CONF_WEIGHT_MARGIN,
        "confusion": settings.CONF_WEIGHT_CONFUSION,
    }
    weight_sum = sum(weights.values())
    score = _clamp(sum(weights[name] * signal for name, signal in signals.items()) / weight_sum)

    return ConfidenceResult(score=score, **signals)


__all__ = [
    "ConfidenceResult",
    "NumericCandidate",
    "composite_confidence",
    "expression_candidates_from_asr",
    "is_known_asr_confusion",
    "numeric_candidates_from_asr",
]
