"""Endpoint de santé ``GET /health``.

Sonde de vivacité minimale (sans dépendance externe) : renvoie ``200`` avec un
statut ``ok``, et **rapporte** la dernière dérive de grammaire constatée entre
l'API et le service ASR (cf. ``app.asr.grammar_guard``).

Le ``status`` reste ``ok`` en cas de dérive, délibérément : la sonde est lue par
systemd et par la supervision, et faire échouer la vivacité provoquerait un
redémarrage en boucle là où le service, lui, répond parfaitement. La dérive est
une **anomalie de configuration**, pas une perte de vivacité — elle se signale,
elle ne tue pas le processus.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.asr import grammar_guard

router = APIRouter(tags=["health"])


class GrammarDriftInfo(BaseModel):
    """Versions divergentes entre les deux processus."""

    api_grammar_version: str
    #: ``""`` quand le service ASR ne rapporte pas sa version.
    asr_grammar_version: str
    reason: str


class HealthResponse(BaseModel):
    status: str = "ok"
    grammar_version: str = ""
    #: ``None`` tant que les deux grammaires concordent.
    grammar_drift: GrammarDriftInfo | None = None


@router.get("/health", response_model=HealthResponse, summary="Sonde de santé")
def health() -> HealthResponse:
    mismatch = grammar_guard.current_mismatch()
    return HealthResponse(
        status="ok",
        grammar_version=grammar_guard.api_grammar_version(),
        grammar_drift=(
            None
            if mismatch is None
            else GrammarDriftInfo(
                api_grammar_version=mismatch.api_grammar_version,
                asr_grammar_version=mismatch.asr_grammar_version,
                reason=mismatch.reason,
            )
        ),
    )
