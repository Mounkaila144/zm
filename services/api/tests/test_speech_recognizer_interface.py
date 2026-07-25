"""Unit tests for SpeechRecognizer interface and MockRecognizer implementation.

These tests validate the ASR abstraction layer (story 2.2):
- Protocol compliance (AC1)
- MockRecognizer behavior (AC2)
- Factory selection (AC3)
- All validation requirements (AC4)
"""

from typing import Protocol

import pytest
from app.asr.base import AsrResult, AudioInput, Candidate, SpeechRecognizer
from app.asr.factory import get_recognizer
from app.asr.mock import MockRecognizer
from app.config import Settings
from pydantic import ValidationError


class TestSpeechRecognizerProtocol:
    """Test that SpeechRecognizer Protocol is well-defined and MockRecognizer complies."""

    def test_speech_recognizer_is_protocol(self) -> None:
        """SpeechRecognizer should be a typing.Protocol."""
        assert isinstance(SpeechRecognizer, type(Protocol))

    def test_mock_recognizer_protocol_compliance(self) -> None:
        """MockRecognizer should implement SpeechRecognizer Protocol (duck typing)."""
        recognizer = MockRecognizer()
        assert isinstance(recognizer, SpeechRecognizer)


class TestAudioInputModel:
    """Test AudioInput Pydantic model validation."""

    def test_audio_input_with_data(self) -> None:
        """AudioInput should accept bytes data."""
        audio = AudioInput(data=b"dummy_audio_data")
        assert audio.data == b"dummy_audio_data"
        assert audio.format == "wav"  # default

    def test_audio_input_with_custom_format(self) -> None:
        """AudioInput should accept custom format."""
        audio = AudioInput(data=b"data", format="mp3")
        assert audio.format == "mp3"

    def test_audio_input_requires_data(self) -> None:
        """AudioInput should require data field."""
        with pytest.raises(ValidationError):
            AudioInput()  # type: ignore


class TestAsrResultModel:
    """Test AsrResult Pydantic model validation."""

    def test_asr_result_minimal(self) -> None:
        """AsrResult should accept minimal required fields."""
        result = AsrResult(
            text="test", acoustic_score=0.9, latency_ms=100, model_version="mock-1.0.0"
        )
        assert result.text == "test"
        assert result.acoustic_score == 0.9
        assert result.latency_ms == 100
        assert result.model_version == "mock-1.0.0"
        assert result.candidates == []

    def test_asr_result_with_candidates(self) -> None:
        """AsrResult should accept candidates list."""
        candidates = [
            Candidate(number=None, text="alternative", score=0.8),
            Candidate(number=42, text="forty two", score=0.7),
        ]
        result = AsrResult(
            text="test",
            acoustic_score=0.9,
            candidates=candidates,
            latency_ms=100,
            model_version="mock-1.0.0",
        )
        assert len(result.candidates) == 2
        assert result.candidates[0].text == "alternative"
        assert result.candidates[1].number == 42

    def test_asr_result_acoustic_score_range(self) -> None:
        """AsrResult should validate acoustic_score between 0 and 1."""
        with pytest.raises(ValidationError):
            AsrResult(text="test", acoustic_score=1.5, latency_ms=100, model_version="mock")

        with pytest.raises(ValidationError):
            AsrResult(text="test", acoustic_score=-0.1, latency_ms=100, model_version="mock")


class TestMockRecognizer:
    """Test MockRecognizer implementation (AC2)."""

    def test_default_initialization(self) -> None:
        """MockRecognizer should initialize with empty text and score 1.0."""
        recognizer = MockRecognizer()
        audio = AudioInput(data=b"test")
        result = recognizer.transcribe(audio)

        assert result.text == ""
        assert result.acoustic_score == 1.0
        assert result.latency_ms == 50
        assert result.model_version == "mock-1.0.0"
        assert result.candidates == []

    def test_set_text_configures_transcription(self) -> None:
        """set_text should configure the transcription returned by transcribe."""
        recognizer = MockRecognizer()
        recognizer.set_text("zangu", acoustic_score=0.95)

        audio = AudioInput(data=b"test")
        result = recognizer.transcribe(audio)

        assert result.text == "zangu"
        assert result.acoustic_score == 0.95

    def test_set_text_default_acoustic_score(self) -> None:
        """set_text should default acoustic_score to 1.0 if not specified."""
        recognizer = MockRecognizer()
        recognizer.set_text("test")

        audio = AudioInput(data=b"test")
        result = recognizer.transcribe(audio)

        assert result.acoustic_score == 1.0

    def test_transcribe_determinism(self) -> None:
        """MockRecognizer should be deterministic: same text → same result."""
        recognizer = MockRecognizer()
        recognizer.set_text("bonga", acoustic_score=0.85)

        audio = AudioInput(data=b"test")
        result1 = recognizer.transcribe(audio)
        result2 = recognizer.transcribe(audio)

        assert result1.text == result2.text == "bonga"
        assert result1.acoustic_score == result2.acoustic_score == 0.85

    def test_transcribe_returns_valid_asr_result(self) -> None:
        """transcribe should return valid AsrResult with all required fields (AC4)."""
        recognizer = MockRecognizer()
        recognizer.set_text("test_text")

        audio = AudioInput(data=b"test")
        result = recognizer.transcribe(audio)

        # Required fields present
        assert hasattr(result, "text")
        assert hasattr(result, "acoustic_score")
        assert hasattr(result, "candidates")
        assert hasattr(result, "latency_ms")
        assert hasattr(result, "model_version")

        # Types correct
        assert isinstance(result.text, str)
        assert isinstance(result.acoustic_score, float)
        assert isinstance(result.candidates, list)
        assert isinstance(result.latency_ms, int)
        assert isinstance(result.model_version, str)

        # Values valid
        assert 0.0 <= result.acoustic_score <= 1.0
        assert result.latency_ms >= 0
        assert result.model_version == "mock-1.0.0"

    def test_model_version_property(self) -> None:
        """model_version property should return 'mock-1.0.0' (AC4)."""
        recognizer = MockRecognizer()
        assert recognizer.model_version == "mock-1.0.0"

    def test_mock_recognizer_no_external_dependencies(self) -> None:
        """MockRecognizer should have no external dependencies (AC2)."""
        # This test passes if the module imports without GPU/httpx
        # Already verified by the imports at the top of this file
        recognizer = MockRecognizer()
        assert isinstance(recognizer, MockRecognizer)


class TestCandidateModel:
    """Test Candidate Pydantic model."""

    def test_candidate_with_number(self) -> None:
        """Candidate should accept parsed number."""
        candidate = Candidate(number=42, text="forty two", score=0.9)
        assert candidate.number == 42
        assert candidate.text == "forty two"
        assert candidate.score == 0.9

    def test_candidate_without_number(self) -> None:
        """Candidate should accept None for number."""
        candidate = Candidate(number=None, text="hello", score=0.8)
        assert candidate.number is None
        assert candidate.text == "hello"

    def test_candidate_score_validation(self) -> None:
        """Candidate score should be between 0 and 1."""
        with pytest.raises(ValidationError):
            Candidate(number=None, text="test", score=1.5)


class TestFactory:
    """Test get_recognizer factory function (AC3)."""

    def test_factory_returns_mock_recognizer(self) -> None:
        """get_recognizer with ASR_MODE='mock' should return MockRecognizer."""
        settings = Settings(ASR_MODE="mock")
        recognizer = get_recognizer(settings)

        assert isinstance(recognizer, MockRecognizer)
        assert recognizer.model_version == "mock-1.0.0"

    def test_factory_supports_remote_modes(self) -> None:
        """ctc/llm are now config-driven remote recognizers (Epic 5, story 5.3)."""
        from app.asr.remote import RemoteCtcRecognizer, RemoteLlmRecognizer

        ctc = get_recognizer(Settings(ASR_MODE="ctc", ASR_ENDPOINT_URL="https://asr.test"))
        llm = get_recognizer(Settings(ASR_MODE="llm", ASR_ENDPOINT_URL="https://asr.test"))
        assert isinstance(ctc, RemoteCtcRecognizer)
        assert isinstance(llm, RemoteLlmRecognizer)

    def test_factory_invalid_mode_raises_error(self) -> None:
        """get_recognizer with invalid ASR_MODE should raise ValidationError."""
        with pytest.raises(ValidationError):
            Settings(ASR_MODE="invalid_mode")  # type: ignore


class TestIntegration:
    """Integration tests for ASR module."""

    def test_full_workflow_mock(self) -> None:
        """Test full workflow: factory → configure → transcribe → validate."""
        # Setup via factory
        settings = Settings(ASR_MODE="mock")
        recognizer = get_recognizer(settings)

        # Configure
        recognizer.set_text("irkanan", acoustic_score=0.92)

        # Execute
        audio = AudioInput(data=b"test_audio")
        result = recognizer.transcribe(audio)

        # Validate
        assert result.text == "irkanan"
        assert result.acoustic_score == 0.92
        assert result.model_version == "mock-1.0.0"
        assert isinstance(result.latency_ms, int)
        assert isinstance(result.candidates, list)


# --- ASR_MOCK_TEXT : confort de dev, sans effet hors du mock (story 6.1) ---


def test_mock_recognizer_is_silent_by_default():
    """Défaut inchangé : le mock ne transcrit rien, donc le pipeline dit `repeat`."""
    from app.asr.base import AudioInput
    from app.asr.factory import get_recognizer
    from app.config import Settings

    recognizer = get_recognizer(Settings(ASR_MODE="mock"))
    assert recognizer.transcribe(AudioInput(data=b"", format="wav")).text == ""


def test_mock_text_is_returned_when_configured():
    from app.asr.base import AudioInput
    from app.asr.factory import get_recognizer
    from app.config import Settings

    settings = Settings(ASR_MODE="mock", ASR_MOCK_TEXT="waranka cindi hinza")
    recognizer = get_recognizer(settings)
    assert recognizer.transcribe(AudioInput(data=b"", format="wav")).text == ("waranka cindi hinza")


def test_mock_text_has_no_effect_on_a_real_recognizer():
    """Garde-fou : la commodité de dev ne doit jamais atteindre le mode réel."""
    from app.asr.factory import get_recognizer
    from app.asr.remote import RemoteCtcRecognizer
    from app.config import Settings

    settings = Settings(
        ASR_MODE="ctc",
        ASR_ENDPOINT_URL="https://example.invalid/transcribe",
        ASR_MOCK_TEXT="waranka cindi hinza",
    )
    assert isinstance(get_recognizer(settings), RemoteCtcRecognizer)
