"""Base ASR interface: Protocol SpeechRecognizer + Pydantic models.

This module defines the core abstractions for Automatic Speech Recognition (ASR).
The SpeechRecognizer Protocol ensures interchangeability of ASR implementations
(NFR9), while Pydantic models provide type safety and serialization.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class AudioInput(BaseModel):
    """Audio PCM16 mono 16kHz en mémoire (bytes) ou chemin fichier.

    In story 2.2, data contains dummy bytes for testing.
    In story 2.4+, data will contain validated decoded audio bytes.
    """

    data: bytes = Field(..., description="Raw audio data bytes (PCM16 mono 16kHz)")
    format: str = Field(default="wav", description="Audio format for extensibility")


class Candidate(BaseModel):
    """Candidat alternatif de reconnaissance.

    The number field is parsed int|None (not raw text) because ASR models
    only return text — number parsing happens later in the API pipeline (story 2.3).
    """

    number: int | None = Field(None, description="Parsed number if numeric, None otherwise")
    text: str = Field(..., description="Alternative transcription text")
    score: float = Field(..., description="Confidence score for this candidate", ge=0.0, le=1.0)


class AsrResult(BaseModel):
    """Résultat brut de reconnaissance (avant normalisation).

    This is the raw output from the ASR engine before any number parsing
    or normalization. The model_version field enables tracking and reproducibility (NFR12).
    """

    text: str = Field(..., description="Raw ASR transcription text")
    acoustic_score: float = Field(..., description="Model confidence score 0-1", ge=0.0, le=1.0)
    candidates: list[Candidate] = Field(
        default_factory=list, description="Alternative candidates (CTC/LLM)"
    )
    latency_ms: int = Field(..., description="ASR processing latency in milliseconds", ge=0)
    model_version: str = Field(..., description="ASR model version identifier")
    #: Version du lexique chargée par le service ASR. Vide si le recognizer ne
    #: la rapporte pas (mock, ou service antérieur à la vérification). Comparée
    #: à celle de l'API par ``app.asr.grammar_guard`` : quand les deux processus
    #: divergent, le décodeur émet des mots que l'analyseur ne lit plus et tout
    #: devient ``repeat`` sans la moindre erreur visible.
    grammar_version: str = Field(default="", description="ASR-side lexicon version")

    model_config = {"protected_namespaces": ()}


@runtime_checkable
class SpeechRecognizer(Protocol):
    """Contrat abstrait pour reconnaissance vocale — remplaçable (NFR9).

    This Protocol defines the interface that all ASR implementations must follow.
    It enables the Strategy/Adapter pattern — swap implementations by configuration
    without changing the API (NFR9: replaceability).

    Implementations:
    - MockRecognizer (story 2.2): Deterministic mock for testing
    - RemoteCtcRecognizer (Epic 5): Real CTC model via HTTP
    - RemoteLlmRecognizer (Epic 5): Real LLM model via HTTP
    """

    def transcribe(self, audio: AudioInput) -> AsrResult:
        """Transcribe audio to text with acoustic signals and metadata.

        Args:
            audio: Audio input containing raw PCM16 mono 16kHz bytes

        Returns:
            AsrResult with text, acoustic score, candidates, latency, and model version
        """
        ...

    @property
    def model_version(self) -> str:
        """Return the model version identifier (e.g., 'mock-1.0.0', 'omniASR_CTC_300M_v2')."""
        ...
