"""Endpoint interne ``GET /api/v1/metrics`` — métriques de pilotage qualité.

Transforme les données déjà persistées (``recognitions`` / ``feedbacks``,
story 2.6) et le lexique versionné (Epic 1) en agrégats de pilotage :

- **Taux** confirmation / correction / rejet / repeat ← ``feedbacks.feedback_type``.
- **Latences** totale et ASR (moyenne + percentiles) ← ``recognitions``.
- **Couverture linguistique** ``validé`` vs ``unresolved`` ← lexique ``zarma_numbers``
  (source unique, jamais recalculée à la main — voir ``grammar.build_grammar_info``).

Endpoint **INTERNE** (observabilité / pilotage) : il n'est pas destiné au mobile
grand public. Il n'expose que des **agrégats** — jamais d'``anon_id`` individuel,
de texte brut ni d'audio (NFR6 — logs/sorties sans PII).
"""

from __future__ import annotations

import math
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from structlog import get_logger

from app.api.v1.grammar import build_grammar_info
from app.db.repositories import MetricsRepo, get_metrics_repo

log = get_logger("zarma.api")

router = APIRouter(tags=["metrics"])

#: Types de feedback reconnus (aligné sur la contrainte DB ``ck_feedbacks_type``).
FEEDBACK_TYPES = ("confirmed", "corrected", "rejected", "repeat_requested")


class RateMetrics(BaseModel):
    """Taux dérivés des feedbacks (agrégats, aucune PII)."""

    total_feedbacks: int
    counts: dict[str, int]
    confirmation_rate: float
    correction_rate: float
    rejection_rate: float
    repeat_rate: float


class LatencySummary(BaseModel):
    """Résumé statistique d'une latence en millisecondes."""

    count: int
    avg_ms: float | None
    p50_ms: int | None
    p95_ms: int | None
    min_ms: int | None
    max_ms: int | None


class LatencyMetrics(BaseModel):
    total: LatencySummary
    asr: LatencySummary


class CoverageMetrics(BaseModel):
    """Couverture linguistique issue du lexique (source unique)."""

    grammar_version: str
    validated_count: int
    unresolved_count: int
    total_items: int
    validated_ratio: float


class MetricsResponse(BaseModel):
    grammar_version: str
    feedback: RateMetrics
    latency: LatencyMetrics
    coverage: CoverageMetrics


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _percentile(values: list[int], fraction: float) -> int | None:
    """Percentile par rang le plus proche (nearest-rank), portable et sans dép."""

    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def _summarize_latency(values: list[int]) -> LatencySummary:
    if not values:
        return LatencySummary(
            count=0, avg_ms=None, p50_ms=None, p95_ms=None, min_ms=None, max_ms=None
        )
    return LatencySummary(
        count=len(values),
        avg_ms=round(sum(values) / len(values), 2),
        p50_ms=_percentile(values, 0.50),
        p95_ms=_percentile(values, 0.95),
        min_ms=min(values),
        max_ms=max(values),
    )


def _build_rate_metrics(counts: dict[str, int]) -> RateMetrics:
    normalized = {feedback_type: counts.get(feedback_type, 0) for feedback_type in FEEDBACK_TYPES}
    total = sum(normalized.values())
    return RateMetrics(
        total_feedbacks=total,
        counts=normalized,
        confirmation_rate=_ratio(normalized["confirmed"], total),
        correction_rate=_ratio(normalized["corrected"], total),
        rejection_rate=_ratio(normalized["rejected"], total),
        repeat_rate=_ratio(normalized["repeat_requested"], total),
    )


def _build_coverage_metrics() -> CoverageMetrics:
    info = build_grammar_info()
    validated = info.validated_count
    unresolved = len(info.unresolved_items)
    total = validated + unresolved
    return CoverageMetrics(
        grammar_version=info.grammar_version,
        validated_count=validated,
        unresolved_count=unresolved,
        total_items=total,
        validated_ratio=_ratio(validated, total),
    )


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="[INTERNE] Métriques de qualité issues du feedback",
    description=(
        "Endpoint interne d'observabilité/pilotage (pas destiné au mobile grand "
        "public). N'expose que des agrégats : taux (confirmation/correction/rejet), "
        "latences (totale/ASR) et couverture linguistique. Aucune PII."
    ),
)
async def metrics(
    repo: Annotated[MetricsRepo, Depends(get_metrics_repo)],
) -> MetricsResponse:
    counts = await repo.feedback_counts()
    total_latencies, asr_latencies = await repo.latency_values()

    feedback_metrics = _build_rate_metrics(counts)
    latency_metrics = LatencyMetrics(
        total=_summarize_latency(total_latencies),
        asr=_summarize_latency(asr_latencies),
    )
    coverage_metrics = _build_coverage_metrics()

    response = MetricsResponse(
        grammar_version=coverage_metrics.grammar_version,
        feedback=feedback_metrics,
        latency=latency_metrics,
        coverage=coverage_metrics,
    )

    # Log structuré des agrégats (sans PII) pour Uptime Kuma / observabilité.
    log.info(
        "metrics_snapshot",
        grammar_version=response.grammar_version,
        total_feedbacks=feedback_metrics.total_feedbacks,
        confirmation_rate=feedback_metrics.confirmation_rate,
        correction_rate=feedback_metrics.correction_rate,
        rejection_rate=feedback_metrics.rejection_rate,
        latency_total_p95_ms=latency_metrics.total.p95_ms,
        latency_asr_p95_ms=latency_metrics.asr.p95_ms,
        validated_ratio=coverage_metrics.validated_ratio,
    )
    return response


__all__ = ["router"]
