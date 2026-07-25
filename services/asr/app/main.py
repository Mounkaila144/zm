"""App Modal : sert les modèles Omnilingual ASR derrière ``POST /transcribe``.

Contrat (encapsulé côté API par ``RemoteCtcRecognizer`` / ``RemoteLlmRecognizer``) :

    POST /transcribe                (HTTPS Modal, secret Bearer)
    multipart:
      - audio : WAV PCM16 mono 16 kHz
      - model : "omniASR_CTC_300M_v2" | "omniASR_LLM_300M_v2"
      - lang  : JSON, ex. ["dje_Latn"]  (LLM uniquement ; absent pour CTC)
    200 : { text, acoustic_score, candidates[], latency_ms, model_version }

Deux modèles chargés **dans** ce service (poids Apache 2.0), pas comme API tierce :
- CTC ``omniASR_CTC_300M_v2`` — **sans** ``lang`` ;
- LLM ``omniASR_LLM_300M_v2`` — ``lang=["dje_Latn"]``.

⚠️ Ce module s'exécute sur la ressource **GPU** (Modal) — il n'est ni importé ni
testé par la CI standard (sans GPU). Le point d'inférence réel est marqué
``_transcribe_array`` : c'est le seul endroit à adapter à l'API exacte du paquet
``omnilingual_asr`` retenu, sans changer le contrat ci-dessus.
"""

from __future__ import annotations

import io
import json
import time
import wave

import modal

CTC_MODEL = "omniASR_CTC_300M_v2"
LLM_MODEL = "omniASR_LLM_300M_v2"
TARGET_SAMPLE_RATE = 16_000

# Image lourde et **séparée** de l'API : torch + Omnilingual ASR + soundfile.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libsndfile1", "ffmpeg")
    .pip_install(
        "torch",
        "torchaudio",
        "numpy",
        "soundfile",
        "omnilingual-asr",  # paquet Meta (fairseq2) — poids Apache 2.0
    )
)

app = modal.App("zarma-asr")

# Secret partagé (créé via `modal secret create zarma-asr-token ASR_ENDPOINT_TOKEN=…`).
_auth = modal.Secret.from_name("zarma-asr-token")


def _decode_wav(raw: bytes) -> tuple[object, int]:
    """Décode un WAV PCM16 mono 16 kHz en tableau float32 [-1, 1]."""

    import numpy as np

    with wave.open(io.BytesIO(raw), "rb") as reader:
        sample_rate = reader.getframerate()
        frames = reader.readframes(reader.getnframes())
    samples = np.frombuffer(frames, dtype="<i2").astype("float32") / 32768.0
    return samples, sample_rate


@app.cls(image=image, gpu="A10G", secrets=[_auth], scaledown_window=300)
class OmnilingualAsr:
    """Charge CTC et LLM une seule fois par conteneur (scale-to-zero géré par Modal)."""

    @modal.enter()
    def load(self) -> None:
        # Chargement réel des deux modèles Omnilingual (une fois par conteneur).
        from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline

        self._pipelines = {
            CTC_MODEL: ASRInferencePipeline(model_card=CTC_MODEL),
            LLM_MODEL: ASRInferencePipeline(model_card=LLM_MODEL),
        }

    def _transcribe_array(self, samples, sample_rate: int, model: str, lang: list[str] | None):
        """Point d'inférence réel — seul endroit dépendant de l'API du modèle.

        CTC : appel **sans** ``lang``. LLM : ``lang=["dje_Latn"]``. Retourne
        ``(text, acoustic_score, candidates)`` où ``candidates`` est une liste de
        ``{text, score}`` triée par score décroissant.
        """

        pipeline = self._pipelines[model]
        kwargs = {} if lang is None else {"lang": lang}
        hypotheses = pipeline.transcribe(samples, sample_rate=sample_rate, **kwargs)
        best = hypotheses[0]
        candidates = [{"text": h.text, "score": float(h.score)} for h in hypotheses[1:]]
        return best.text, float(best.score), candidates

    @modal.fastapi_endpoint(method="POST", requires_proxy_auth=True)
    async def transcribe(self, request):  # noqa: ANN001 - Starlette Request (runtime GPU)
        from fastapi.responses import JSONResponse

        started = time.perf_counter()
        form = await request.form()
        model = form.get("model", CTC_MODEL)
        if model not in (CTC_MODEL, LLM_MODEL):
            return JSONResponse({"error": "unknown_model"}, status_code=400)
        lang = json.loads(form["lang"]) if form.get("lang") else None

        upload = form["audio"]
        raw = await upload.read()
        samples, sample_rate = _decode_wav(raw)
        text, acoustic_score, candidates = self._transcribe_array(samples, sample_rate, model, lang)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return JSONResponse(
            {
                "text": text,
                "acoustic_score": acoustic_score,
                "candidates": candidates,
                "latency_ms": latency_ms,
                "model_version": model,
            }
        )
