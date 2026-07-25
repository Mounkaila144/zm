"""Smoke test **réel** de bout en bout sur la ressource GPU retenue (story 5.3 AC4).

Hors CI standard : il exige un endpoint ASR déployé et un audio réel. Il est
**skippé** automatiquement si l'environnement n'est pas configuré, de sorte qu'un
``pytest`` accidentel sur ce dossier ne casse pas la CI (sans GPU).

Exécution manuelle (après `modal deploy services/asr/app/main.py`) :

    ASR_ENDPOINT_URL=https://…modal.run \
    ASR_ENDPOINT_TOKEN=… \
    ASR_SMOKE_AUDIO=dataset/benchmark/<echantillon>.wav \
    ASR_SMOKE_EXPECTED=372 \
    uv run pytest services/asr/tests/smoke_real_recognizer.py -q

Le test confirme le contrat ``/transcribe`` et l'intégration via
``RemoteCtcRecognizer`` : au moins un nombre correctement transcrit.
"""

from __future__ import annotations

import os
import sys
import wave
from pathlib import Path

import pytest

# Rend le paquet ``app`` de l'API importable (RemoteRecognizer + Settings).
_API_ROOT = Path(__file__).resolve().parents[2] / "api"
if _API_ROOT.is_dir() and str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

_ENDPOINT = os.environ.get("ASR_ENDPOINT_URL")
_AUDIO = os.environ.get("ASR_SMOKE_AUDIO")

pytestmark = pytest.mark.skipif(
    not (_ENDPOINT and _AUDIO and Path(_AUDIO).is_file()),
    reason="Smoke GPU réel : requiert ASR_ENDPOINT_URL + ASR_SMOKE_AUDIO (hors CI).",
)


def _pcm_from_wav(path: Path) -> bytes:
    with wave.open(str(path), "rb") as reader:
        assert reader.getnchannels() == 1
        assert reader.getframerate() == 16_000
        assert reader.getsampwidth() == 2
        return reader.readframes(reader.getnframes())


@pytest.mark.parametrize("asr_mode", ["ctc", "llm"])
def test_real_transcription_end_to_end(asr_mode: str) -> None:
    import zarma_numbers
    from app.asr.base import AudioInput
    from app.asr.factory import get_recognizer
    from app.config import Settings

    settings = Settings(
        ASR_MODE=asr_mode,
        ASR_ENDPOINT_URL=_ENDPOINT,
        ASR_ENDPOINT_TOKEN=os.environ.get("ASR_ENDPOINT_TOKEN", ""),
    )
    recognizer = get_recognizer(settings)
    pcm = _pcm_from_wav(Path(_AUDIO))

    result = recognizer.transcribe(AudioInput(data=pcm, format="pcm_s16le"))

    assert result.text  # une transcription réelle est revenue
    assert result.model_version
    number = zarma_numbers.parse(zarma_numbers.normalize(result.text))
    expected = os.environ.get("ASR_SMOKE_EXPECTED")
    if expected is not None:
        assert number == int(expected), f"{result.text!r} → {number}, attendu {expected}"
    else:
        assert number is not None, f"aucun nombre reconnu dans {result.text!r}"
