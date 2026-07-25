"""ASR module: SpeechRecognizer abstraction with implementations.

Public exports:
- SpeechRecognizer: Protocol for ASR implementations
- AudioInput, AsrResult, Candidate: Pydantic models
- get_recognizer: Factory for ASR implementation selection
"""

from app.asr.base import AsrResult, AudioInput, Candidate, SpeechRecognizer
from app.asr.factory import get_recognizer

__all__ = [
    "SpeechRecognizer",
    "AudioInput",
    "AsrResult",
    "Candidate",
    "get_recognizer",
]
