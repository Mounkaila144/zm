"""MockRecognizer: Deterministic ASR implementation for testing and development.

This module provides a zero-dependency, deterministic mock implementation of
SpeechRecognizer. It's used for development and testing without requiring GPU
or real ASR models (NFR1: no GPU for development).
"""

from __future__ import annotations

from collections.abc import Sequence

from app.asr.base import AsrResult, AudioInput, Candidate


class MockRecognizer:
    """Implémentation déterministe pour tests/dev — sans GPU ni dépendance externe.

    MockRecognizer is a pure algorithmic implementation with zero external
    dependencies (no httpx, no PyTorch, no GPU). It returns configurable
    deterministic transcriptions for testing (AC2).

    Usage:
        recognizer = MockRecognizer()
        recognizer.set_text("zangu", acoustic_score=0.95)
        result = recognizer.transcribe(audio_input)
        assert result.text == "zangu"
    """

    def __init__(self) -> None:
        """Initialize MockRecognizer with default empty transcription."""
        self._text = ""
        self._acoustic_score = 1.0
        self._candidates: list[Candidate] = []

    def set_text(self, text: str, acoustic_score: float = 1.0) -> None:
        """Configure la transcription retournée par transcribe() — déterministe pour tests.

        Args:
            text: The transcription text to return
            acoustic_score: Confidence score 0-1 (default 1.0)
        """
        self._text = text
        self._acoustic_score = acoustic_score

    def set_candidates(self, candidates: Sequence[Candidate]) -> None:
        """Configure une copie des alternatives retournées par ``transcribe``."""

        self._candidates = list(candidates)

    def transcribe(self, audio: AudioInput) -> AsrResult:
        """Retourne un résultat configuré — candidates vide (pas de modèle réel).

        Args:
            audio: Audio input (ignored in mock, only interface compliance)

        Returns:
            AsrResult with configured text, acoustic_score, empty candidates,
            simulated latency, and model version
        """
        return AsrResult(
            text=self._text,
            acoustic_score=self._acoustic_score,
            candidates=list(self._candidates),
            latency_ms=50,  # Simulated latency
            model_version=self.model_version,
        )

    @property
    def model_version(self) -> str:
        """Return the mock model version identifier."""
        return "mock-1.0.0"
