"""Tests des recognizers distants (CTC/LLM) — httpx mocké, sans GPU ni réseau."""

from __future__ import annotations

import httpx
import pytest
from app.asr.base import AudioInput, SpeechRecognizer
from app.asr.factory import get_recognizer
from app.asr.remote import RemoteCtcRecognizer, RemoteLlmRecognizer
from app.config import Settings
from app.pipeline.recognition import run_recognition_pipeline
from pydantic import ValidationError

ENDPOINT = "https://asr.example.test"
PCM = b"\x01\x00\x02\x00\x03\x00\x04\x00"  # 4 échantillons PCM16 factices


def _settings(mode: str = "ctc", *, url: str = ENDPOINT, token: str = "s3cret") -> Settings:
    return Settings(ASR_MODE=mode, ASR_ENDPOINT_URL=url, ASR_ENDPOINT_TOKEN=token)


def _ok_payload() -> dict:
    return {
        "text": "zangou hinza",
        "acoustic_score": 0.9,
        "candidates": [{"text": "zangou hinka", "score": 0.4, "number": None}],
        "latency_ms": 123,
        "model_version": "omniASR_CTC_300M_v2",
    }


class _Recorder:
    """Capture la dernière requête et renvoie une réponse programmée."""

    def __init__(self, response: httpx.Response | Exception) -> None:
        self._response = response
        self.request: httpx.Request | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.request = request
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def test_maps_transcribe_response_to_asr_result() -> None:
    recorder = _Recorder(httpx.Response(200, json=_ok_payload()))
    recognizer = RemoteCtcRecognizer(_settings(), transport=httpx.MockTransport(recorder))

    result = recognizer.transcribe(AudioInput(data=PCM, format="pcm_s16le"))

    assert result.text == "zangou hinza"
    assert result.acoustic_score == 0.9
    assert result.latency_ms == 123
    assert result.model_version == "omniASR_CTC_300M_v2"
    assert result.candidates[0].text == "zangou hinka"
    assert result.candidates[0].score == 0.4


def test_wraps_pcm_into_wav_and_sends_auth() -> None:
    recorder = _Recorder(httpx.Response(200, json=_ok_payload()))
    recognizer = RemoteCtcRecognizer(_settings(), transport=httpx.MockTransport(recorder))

    recognizer.transcribe(AudioInput(data=PCM, format="pcm_s16le"))

    assert recorder.request is not None
    assert recorder.request.url.path.endswith("/transcribe")
    assert recorder.request.headers["Authorization"] == "Bearer s3cret"
    body = recorder.request.content
    assert b"RIFF" in body and b"WAVE" in body  # PCM emballé en WAV
    assert b"omniASR_CTC_300M_v2" in body


def test_ctc_omits_lang_llm_sends_dje_latn() -> None:
    ctc_recorder = _Recorder(httpx.Response(200, json=_ok_payload()))
    RemoteCtcRecognizer(_settings("ctc"), transport=httpx.MockTransport(ctc_recorder)).transcribe(
        AudioInput(data=PCM, format="pcm_s16le")
    )
    assert b"dje_Latn" not in ctc_recorder.request.content  # CTC : aucune langue

    llm_recorder = _Recorder(httpx.Response(200, json=_ok_payload()))
    RemoteLlmRecognizer(_settings("llm"), transport=httpx.MockTransport(llm_recorder)).transcribe(
        AudioInput(data=PCM, format="pcm_s16le")
    )
    assert b"dje_Latn" in llm_recorder.request.content  # LLM : lang imposée


@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(500, text="boom"),
        httpx.ConnectError("refused"),
        httpx.TimeoutException("cold start"),
    ],
)
def test_failure_falls_back_to_repeat(failure) -> None:
    recognizer = RemoteCtcRecognizer(_settings(), transport=httpx.MockTransport(_Recorder(failure)))

    result = recognizer.transcribe(AudioInput(data=PCM, format="pcm_s16le"))

    # Repli sûr : texte vide, aucun nombre inventé.
    assert result.text == ""
    assert result.acoustic_score == 0.0
    assert result.model_version == "omniASR_CTC_300M_v2"
    # Le pipeline en déduit repeat (aucun nombre).
    outcome = run_recognition_pipeline(result, _settings())
    assert outcome.number is None
    assert outcome.decision == "repeat"


def test_no_internal_error_leaks_on_failure() -> None:
    recognizer = RemoteCtcRecognizer(
        _settings(), transport=httpx.MockTransport(_Recorder(httpx.ConnectError("secret host")))
    )
    result = recognizer.transcribe(AudioInput(data=PCM, format="pcm_s16le"))
    assert "secret host" not in result.text


def test_factory_selects_remote_by_config() -> None:
    ctc = get_recognizer(_settings("ctc"))
    llm = get_recognizer(_settings("llm"))
    assert isinstance(ctc, RemoteCtcRecognizer)
    assert isinstance(llm, RemoteLlmRecognizer)
    assert isinstance(ctc, SpeechRecognizer)  # respecte le Protocol
    assert ctc.model_version == "omniASR_CTC_300M_v2"
    assert llm.model_version == "omniASR_LLM_300M_v2"


def test_remote_mode_requires_endpoint_url() -> None:
    # La config refuse ctc/llm sans endpoint.
    with pytest.raises(ValidationError):
        Settings(ASR_MODE="ctc", ASR_ENDPOINT_URL="")
    # La classe elle-même refuse un endpoint vide (garde défensive).
    with pytest.raises(ValueError):
        RemoteCtcRecognizer(Settings(ASR_MODE="mock", ASR_ENDPOINT_URL=""))
