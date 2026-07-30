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

**Décodage contraint (story 5.6)** — le chemin CTC ne fait plus d'``argmax``
trame par trame : les logits alimentent une recherche en faisceau restreinte à
la grammaire zarma (``services/asr/app/decoding.py``) — celle des **nombres**
par défaut, celle des **expressions arithmétiques** si ``DECODE_GRAMMAR`` vaut
``expressions`` (calculatrice vocale, story 6.1). Le décodage
a lieu **ici**, là où les logits existent : ils ne traversent jamais le réseau
(``T × 10 288`` flottants, cf. Annexe D §4) et le contrat ci-dessus est
inchangé (NFR9). Seule évolution : ``acoustic_score`` et ``candidates`` portent
désormais de **vrais** scores (auparavant ``1.0`` en dur).

⚠️ Ce module s'exécute sur la ressource **GPU** (Modal) — il n'est ni importé ni
testé par la CI standard (sans GPU). Les deux briques qu'il orchestre sont, elles,
testées sans GPU : ``decoding.py`` et ``transcription.py``. Le point d'inférence
réel est marqué ``_logits`` / ``_transcribe_array`` : c'est le seul endroit à
adapter à l'API exacte du paquet ``omnilingual_asr`` retenu.
"""

from __future__ import annotations

import io
import json
import time
import wave
from pathlib import Path

import modal

CTC_MODEL = "omniASR_CTC_300M_v2"
LLM_MODEL = "omniASR_LLM_300M_v2"
TARGET_SAMPLE_RATE = 16_000

_APP_DIR = str(Path(__file__).resolve().parent)

# Image lourde et **séparée** de l'API : torch + Omnilingual ASR + soundfile.
# ``zarma_numbers`` (paquet pur Python, sans dépendance lourde) est ajouté pour
# que la **grammaire** soit disponible là où le décodage a lieu — source unique,
# jamais réécrite côté service (story 5.6).
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libsndfile1", "ffmpeg")
    .pip_install(
        "torch",
        "torchaudio",
        "numpy",
        "soundfile",
        "pydantic-settings",
        "omnilingual-asr",  # paquet Meta (fairseq2) — poids Apache 2.0
    )
    .add_local_python_source("zarma_numbers")
    .add_local_dir(_APP_DIR, remote_path="/root/app")
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

        # --- Décodage contraint (story 5.6) : compilé une fois par conteneur ---
        from zarma_numbers import load_lexicon

        from app.config import AsrSettings
        from app.decoding import ConstrainedCtcDecoder, build_token_lexicon

        self._settings = AsrSettings()
        self._decoder = None
        # Version du lexique de **ce conteneur** : l'API la compare à la sienne
        # pour détecter une dérive entre les deux processus (cf. transcription.py).
        self._grammar_version = load_lexicon().grammar_version
        if self._settings.DECODE_CONSTRAINED:
            encoder = self._pipelines[CTC_MODEL].tokenizer.create_encoder()

            def encode(text: str) -> list[int]:
                # Annexe A §2 : les ids spéciaux bas (<= 3) ne sont pas des
                # étiquettes CTC — on ne garde que les tokens réels.
                ids = encoder(text)
                ids = ids.tolist() if hasattr(ids, "tolist") else list(ids)
                return [int(i) for i in ids if int(i) > 3]

            # Nombres seuls (epics 1–5) ou expressions arithmétiques (story 6.1)
            # selon DECODE_GRAMMAR : le décodeur change de langue, pas
            # d'algorithme, et le contrat /transcribe reste identique.
            grammar = self._settings.load_grammar()
            lexicon = build_token_lexicon(
                grammar,
                encode,
                separator=self._settings.separator_ids(),
                blank_id=self._settings.DECODE_BLANK_ID,
            )
            self._decoder = ConstrainedCtcDecoder(grammar, lexicon, self._settings.decoder_config())

    def _logits(self, samples, sample_rate: int):
        """Logits CTC ``(T, V)`` en numpy — **jamais** exposés hors du service.

        Le pipeline officiel calcule les logits puis les jette
        (``pred_ids = torch.argmax(logits, dim=-1)``). On appelle donc le modèle
        directement, sans passer par ``transcribe`` — pas de *monkeypatch*,
        contrairement au prototype (Annexe A §1).
        """

        import torch

        pipeline = self._pipelines[CTC_MODEL]
        batch = pipeline.build_batch(samples, sample_rate=sample_rate)
        with torch.inference_mode():
            logits, layout = pipeline.model(batch.source_seqs, batch.layout)
        length = int(list(layout.seq_lens)[0])
        return logits[0, :length].detach().float().cpu().numpy()

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

        # Chemin CTC + décodage contraint : la sortie appartient par construction
        # à la grammaire des nombres, ou le service s'abstient (texte vide).
        if model == CTC_MODEL and self._decoder is not None:
            from app.transcription import build_transcribe_payload

            result = self._decoder.decode(self._logits(samples, sample_rate))
            latency_ms = int((time.perf_counter() - started) * 1000)
            return JSONResponse(
                build_transcribe_payload(
                    result,
                    model_version=model,
                    latency_ms=latency_ms,
                    grammar_version=self._grammar_version,
                )
            )

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
