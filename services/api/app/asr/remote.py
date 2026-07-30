"""Recognizers distants (CTC & LLM) branchés derrière ``SpeechRecognizer``.

Ces classes encapsulent **entièrement** le contrat de l'endpoint ASR distant
(Modal) : construction de la requête ``POST /transcribe``, authentification par
secret, timeout explicite, et **repli sûr** en cas d'échec / cold start dépassé.

Repli (NFR14 — jamais de nombre inventé) : sur toute erreur réseau/HTTP/timeout,
``transcribe`` renvoie un ``AsrResult`` à **texte vide** ; le pipeline en déduit
naturellement ``number is None`` → ``decision = repeat``. La panne ASR ne fabrique
donc jamais un nombre et n'expose aucune erreur interne à l'appelant.

Le passage Mock ↔ réel se fait uniquement par configuration (``ASR_MODE``,
``ASR_ENDPOINT_URL``, ``ASR_ENDPOINT_TOKEN``) — aucun changement d'API ni de
mobile (NFR9).
"""

from __future__ import annotations

import io
import json
import wave
from time import perf_counter

import httpx
from structlog import get_logger

from app.asr import grammar_guard
from app.asr.base import AsrResult, AudioInput, Candidate
from app.config import Settings

log = get_logger("zarma.asr")

_TARGET_SAMPLE_RATE = 16_000
_TARGET_CHANNELS = 1
_TARGET_SAMPLE_WIDTH = 2


def _to_wav_bytes(audio: AudioInput) -> bytes:
    """Emballe du PCM16 mono 16 kHz en conteneur WAV ; laisse un WAV intact.

    Le pipeline fournit ``format='pcm_s16le'`` (PCM brut) ; l'endpoint attend un
    WAV PCM16 mono 16 kHz — on encapsule donc les échantillons sans les altérer.
    """

    if audio.format == "wav":
        return audio.data
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(_TARGET_CHANNELS)
        writer.setsampwidth(_TARGET_SAMPLE_WIDTH)
        writer.setframerate(_TARGET_SAMPLE_RATE)
        writer.writeframes(audio.data)
    return buffer.getvalue()


class _RemoteRecognizer:
    """Base commune des recognizers distants (contrat Modal encapsulé)."""

    #: Identifiant de modèle (aussi ``model_version`` par défaut).
    _MODEL_NAME: str = ""
    #: Langue imposée à l'endpoint (``None`` = aucune, cas CTC).
    _LANG: list[str] | None = None

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not settings.ASR_ENDPOINT_URL:
            raise ValueError("ASR_ENDPOINT_URL is required for a remote recognizer")
        self._endpoint = settings.ASR_ENDPOINT_URL.rstrip("/")
        self._token = settings.ASR_ENDPOINT_TOKEN
        self._timeout = settings.ASR_TIMEOUT_SECONDS
        # ``transport`` permet d'injecter un httpx.MockTransport en test (sans réseau).
        self._transport = transport

    @property
    def model_version(self) -> str:
        return self._MODEL_NAME

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    def _form_fields(self) -> dict[str, str]:
        fields = {"model": self._MODEL_NAME}
        if self._LANG is not None:
            fields["lang"] = json.dumps(self._LANG)
        return fields

    def _fallback(self, started: float) -> AsrResult:
        """Résultat dégradé (texte vide) → le pipeline décide ``repeat``."""

        return AsrResult(
            text="",
            acoustic_score=0.0,
            candidates=[],
            latency_ms=max(0, int((perf_counter() - started) * 1000)),
            model_version=self._MODEL_NAME,
        )

    def transcribe(self, audio: AudioInput) -> AsrResult:
        started = perf_counter()
        try:
            wav = _to_wav_bytes(audio)
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(
                    f"{self._endpoint}/transcribe",
                    files={"audio": ("audio.wav", wav, "audio/wav")},
                    data=self._form_fields(),
                    headers=self._headers(),
                )
                response.raise_for_status()
                payload = response.json()
            return self._map_response(payload)
        except (httpx.HTTPError, ValueError, KeyError, wave.Error) as exc:
            # Aucune fuite d'erreur interne ; repli sûr vers ``repeat``.
            log.warning("asr.remote_failed", model=self._MODEL_NAME, error=type(exc).__name__)
            return self._fallback(started)

    def _map_response(self, payload: dict) -> AsrResult:
        candidates = [
            Candidate(
                text=str(item["text"]),
                score=float(item["score"]),
                number=item.get("number"),
            )
            for item in payload.get("candidates", [])
        ]
        # Confronter les deux grammaires à chaque réponse : c'est le seul point
        # du chemin où les deux processus se parlent. La garde journalise et
        # n'interrompt jamais — cf. ``grammar_guard``.
        grammar_version = str(payload.get("grammar_version") or "")
        grammar_guard.check(grammar_version)
        return AsrResult(
            text=str(payload["text"]),
            acoustic_score=float(payload["acoustic_score"]),
            candidates=candidates,
            latency_ms=int(payload.get("latency_ms", 0)),
            model_version=str(payload.get("model_version") or self._MODEL_NAME),
            grammar_version=grammar_version,
        )


class RemoteCtcRecognizer(_RemoteRecognizer):
    """CTC ``omniASR_CTC_300M_v2`` — sans ``lang`` (FR9)."""

    _MODEL_NAME = "omniASR_CTC_300M_v2"
    _LANG = None


class RemoteLlmRecognizer(_RemoteRecognizer):
    """LLM ``omniASR_LLM_300M_v2`` — ``lang=['dje_Latn']`` (FR9)."""

    _MODEL_NAME = "omniASR_LLM_300M_v2"
    _LANG = ["dje_Latn"]


__all__ = ["RemoteCtcRecognizer", "RemoteLlmRecognizer"]
