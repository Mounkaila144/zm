#!/usr/bin/env python3
"""Prépare la consigne « incompris » depuis une prise brute (story 6.x, PTR Niger).

Miroir minimal de `scripts/speech/prepare_bank.py` pour les consignes longues
(une phrase, pas un mot) : mêmes idées — format canonique 16 kHz mono PCM16,
détourage des silences de tête et de queue — mais un seuil de détourage
**lissé** (fenêtre RMS de 50 ms) plutôt qu'échantillon par échantillon. Sur une
phrase de plusieurs secondes, un bruit de fond ponctuel proche du seuil suffit
à tromper un détourage brut ; le lissage l'ignore sans manger le début ou la
fin de la voix.

La source doit déjà être un WAV mono 16 kHz PCM16 (convertir au préalable avec
`afconvert -f WAVE -d LEI16@16000 -c 1 source.wav 16k.wav` sur macOS, ou
l'équivalent ffmpeg/sox ailleurs) : ce script ne rééchantillonne pas, il ne
fait que détourer et écrire au format canonique de l'application.

Usage : python3 tool/build_voice_prompt.py <source_16k.wav> <sortie.wav>
"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

TARGET_RATE = 16_000
TRIM_WINDOW_SECONDS = 0.05
TRIM_THRESHOLD_DB = -34.0
TRIM_MARGIN_SECONDS = 0.15


def load_pcm16_mono(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as reader:
        if reader.getframerate() != TARGET_RATE or reader.getnchannels() != 1:
            raise ValueError(
                f"{path} n'est pas au format canonique "
                f"(attendu {TARGET_RATE} Hz mono) — reconvertir d'abord."
            )
        raw = reader.readframes(reader.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def trim_silence(samples: np.ndarray, rate: int) -> np.ndarray:
    """Retire les silences de tête et de queue via une enveloppe RMS lissée."""
    window = max(1, int(TRIM_WINDOW_SECONDS * rate))
    envelope = np.sqrt(np.convolve(samples**2, np.ones(window) / window, mode="same"))
    peak = float(envelope.max())
    if peak <= 0.0:
        return samples

    threshold = peak * (10.0 ** (TRIM_THRESHOLD_DB / 20.0))
    loud = np.flatnonzero(envelope >= threshold)
    if loud.size == 0:
        return samples

    margin = int(TRIM_MARGIN_SECONDS * rate)
    start = max(0, int(loud[0]) - margin)
    end = min(samples.size, int(loud[-1]) + margin + 1)
    return samples[start:end]


def write_wav(path: Path, samples: np.ndarray) -> None:
    pcm16 = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(TARGET_RATE)
        writer.writeframes(pcm16.tobytes())


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    source, destination = Path(argv[0]), Path(argv[1])
    samples = trim_silence(load_pcm16_mono(source), TARGET_RATE)
    write_wav(destination, samples)
    print(f"{destination}  {samples.size / TARGET_RATE:.2f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
