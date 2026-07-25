"""Tests unitaires et intégration de la confiance/politique (story 2.5)."""

from __future__ import annotations

import wave
from io import BytesIO

import pytest
import zarma_numbers
from app.asr.base import AsrResult, Candidate
from app.asr.factory import get_recognizer
from app.asr.mock import MockRecognizer
from app.config import Settings, get_settings
from app.main import app
from app.pipeline.confidence import (
    NumericCandidate,
    composite_confidence,
    numeric_candidates_from_asr,
)
from app.pipeline.policy import decide
from fastapi.testclient import TestClient

client = TestClient(app)
ANON_ID = "00000000-0000-4000-8000-000000000025"


def make_wav() -> bytes:
    output = BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16_000)
        target.writeframes(b"\x00\x00" * 1_600)
    return output.getvalue()


def make_asr(
    text: str,
    *,
    acoustic_score: float = 0.9,
    candidates: list[Candidate] | None = None,
) -> AsrResult:
    return AsrResult(
        text=text,
        acoustic_score=acoustic_score,
        candidates=candidates or [],
        latency_ms=1,
        model_version="test-1.0.0",
    )


def score(asr: AsrResult, settings: Settings | None = None):
    normalized = zarma_numbers.normalize(asr.text)
    number = zarma_numbers.parse(normalized)
    candidates = numeric_candidates_from_asr(asr)
    return composite_confidence(
        asr=asr,
        normalized_text=normalized,
        number=number,
        numeric_candidates=candidates,
        settings=settings or Settings(),
    )


def post_audio() -> object:
    return client.post(
        "/api/v1/recognize",
        files={"audio": ("confidence.wav", make_wav(), "audio/wav")},
        data={"anon_id": ANON_ID},
    )


@pytest.fixture
def mock_recognizer() -> MockRecognizer:
    recognizer = MockRecognizer()
    app.dependency_overrides[get_recognizer] = lambda: recognizer
    try:
        yield recognizer
    finally:
        app.dependency_overrides.pop(get_recognizer, None)
        app.dependency_overrides.pop(get_settings, None)


class TestCompositeConfidence:
    def test_each_signal_is_exposed_and_bounded(self) -> None:
        canonical = zarma_numbers.generate(100)
        asr = make_asr(
            canonical,
            acoustic_score=0.8,
            candidates=[
                Candidate(number=None, text=zarma_numbers.generate(90), score=0.6),
            ],
        )

        result = score(asr)

        assert result.acoustic == 0.8
        assert result.grammatical == 1.0
        assert result.variant == 1.0
        assert result.margin == pytest.approx(0.2)
        assert result.confusion == 1.0
        assert all(
            0.0 <= signal <= 1.0
            for signal in (
                result.score,
                result.acoustic,
                result.grammatical,
                result.variant,
                result.margin,
                result.confusion,
            )
        )

    def test_unknown_tokens_lower_variant_signal(self) -> None:
        result = score(make_asr(f"{zarma_numbers.generate(100)} unknown"))
        assert result.variant == 0.5
        assert result.grammatical == 0.0

    def test_single_numeric_candidate_has_full_margin(self) -> None:
        result = score(make_asr(zarma_numbers.generate(1)))
        assert result.margin == 1.0

    def test_known_asr_confusion_only_penalizes_confidence(self) -> None:
        asr = make_asr(
            "zangou",
            candidates=[Candidate(number=None, text="zangu", score=0.85)],
        )
        result = score(asr)

        assert result.confusion == 0.0
        assert zarma_numbers.parse("zangu") is None

    def test_configured_weights_change_score(self) -> None:
        settings = Settings(
            CONF_WEIGHT_ACOUSTIC=1.0,
            CONF_WEIGHT_GRAMMAR=0.0,
            CONF_WEIGHT_VARIANT=0.0,
            CONF_WEIGHT_MARGIN=0.0,
            CONF_WEIGHT_CONFUSION=0.0,
        )
        result = score(make_asr(zarma_numbers.generate(1), acoustic_score=0.25), settings)
        assert result.score == 0.25


class TestConfidenceSettings:
    def test_at_least_one_weight_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="confidence weight"):
            Settings(
                CONF_WEIGHT_ACOUSTIC=0.0,
                CONF_WEIGHT_GRAMMAR=0.0,
                CONF_WEIGHT_VARIANT=0.0,
                CONF_WEIGHT_MARGIN=0.0,
                CONF_WEIGHT_CONFUSION=0.0,
            )

    def test_confirm_threshold_must_not_exceed_accept_threshold(self) -> None:
        with pytest.raises(ValueError, match="CONFIRM_THRESHOLD"):
            Settings(POLICY_ACCEPT_THRESHOLD=0.5, POLICY_CONFIRM_THRESHOLD=0.6)


class TestPolicy:
    settings = Settings()
    one = [NumericCandidate(number=1, text="afo", score=0.9)]
    ambiguous = [
        NumericCandidate(number=1, text="afo", score=0.80),
        NumericCandidate(number=2, text="ihinka", score=0.75),
    ]

    def test_non_numeric_always_repeats(self) -> None:
        assert (
            decide(
                score=1.0,
                number=None,
                numeric_candidates=self.one,
                settings=self.settings,
            )
            == "repeat"
        )

    def test_close_numeric_candidates_require_confirmation(self) -> None:
        assert (
            decide(
                score=0.99,
                number=1,
                numeric_candidates=self.ambiguous,
                settings=self.settings,
            )
            == "confirm"
        )

    def test_high_score_is_accepted(self) -> None:
        assert (
            decide(
                score=0.9,
                number=1,
                numeric_candidates=self.one,
                settings=self.settings,
            )
            == "accept"
        )

    def test_medium_score_requires_confirmation(self) -> None:
        assert (
            decide(
                score=0.6,
                number=1,
                numeric_candidates=self.one,
                settings=self.settings,
            )
            == "confirm"
        )

    def test_low_score_repeats(self) -> None:
        assert (
            decide(
                score=0.4,
                number=1,
                numeric_candidates=self.one,
                settings=self.settings,
            )
            == "repeat"
        )


class TestConfidencePolicyIntegration:
    def test_high_confidence_canonical_zangou_is_accepted(
        self, mock_recognizer: MockRecognizer
    ) -> None:
        mock_recognizer.set_text("zangou", acoustic_score=0.95)

        response = post_audio()

        assert response.status_code == 200
        assert response.json()["recognized_number"] == 100
        assert response.json()["decision"] == "accept"
        assert response.json()["confidence"] >= Settings().POLICY_ACCEPT_THRESHOLD

    def test_close_candidates_are_ordered_and_confirmed(
        self, mock_recognizer: MockRecognizer
    ) -> None:
        mock_recognizer.set_text(zarma_numbers.generate(100), acoustic_score=0.80)
        mock_recognizer.set_candidates(
            [
                Candidate(number=None, text=zarma_numbers.generate(90), score=0.75),
                Candidate(number=None, text=zarma_numbers.generate(100), score=0.80),
            ]
        )

        response = post_audio()

        assert response.status_code == 200
        body = response.json()
        assert body["decision"] == "confirm"
        assert [candidate["number"] for candidate in body["alternatives"]] == [100, 90]
        assert [candidate["score"] for candidate in body["alternatives"]] == [0.80, 0.75]

    def test_non_numeric_speech_never_invents_number(self, mock_recognizer: MockRecognizer) -> None:
        mock_recognizer.set_text("salaam", acoustic_score=0.99)

        response = post_audio()

        assert response.status_code == 200
        assert response.json()["recognized_number"] is None
        assert response.json()["decision"] == "repeat"

    def test_zangu_confusion_is_never_applied_automatically(
        self, mock_recognizer: MockRecognizer
    ) -> None:
        mock_recognizer.set_text("zangu", acoustic_score=0.99)

        response = post_audio()

        assert response.status_code == 200
        assert response.json()["recognized_number"] is None
        assert response.json()["normalized_text"] == "zangu"
        assert response.json()["decision"] == "repeat"

    def test_settings_override_can_lower_accept_threshold(
        self, mock_recognizer: MockRecognizer
    ) -> None:
        mock_recognizer.set_text(zarma_numbers.generate(1), acoustic_score=0.30)

        default_response = post_audio()
        app.dependency_overrides[get_settings] = lambda: Settings(POLICY_ACCEPT_THRESHOLD=0.70)
        overridden_response = post_audio()

        assert default_response.json()["decision"] == "confirm"
        assert overridden_response.json()["decision"] == "accept"
