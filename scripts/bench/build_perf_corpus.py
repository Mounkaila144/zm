#!/usr/bin/env python
"""Construit un corpus de benchmark **de performance** à partir de vraie parole zarma.

Pourquoi ce script existe
-------------------------

Le benchmark de latence qui a servi jusqu'ici utilisait un WAV **silencieux** de
8 secondes. C'est trompeur : sur du silence, le faisceau ne contient presque
aucune hypothèse vivante et le rescoring exact ne s'exécute quasiment jamais.
Les journaux de production le montrent sans ambiguïté — 220 à 400 ms de décodage
sur du silence contre 1 100 à 6 800 ms sur de la parole réelle. Mesurer le
silence revient à mesurer le chemin qui n'est jamais emprunté en production.

Ce script produit donc des énoncés **acoustiquement réels** : les 40
enregistrements de mots de ``apps/mobile/assets/voice/words/`` (16 kHz, mono,
PCM16, un locuteur zarma) sont concaténés le long de chemins **valides de la
grammaire**, avec de courtes pauses inter-mots. Ce n'est pas de la parole
continue naturelle — il manque la coarticulation — mais chaque trame est de la
vraie parole zarma, et la transcription attendue est connue par construction.
C'est exactement ce qu'il faut pour mesurer un coût de calcul et détecter une
régression de décodage.

Les cas dégradés (bruit, silences de bord, parole faible, silence total) sont
dérivés des mêmes énoncés pour rester comparables.

Sortie : ``dataset/benchmark/perf/*.wav`` + ``manifest.json`` (texte attendu).
"""

from __future__ import annotations

import argparse
import json
import wave
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
WORDS_DIR = REPO / "apps" / "mobile" / "assets" / "voice" / "words"
SAMPLE_RATE = 16_000

#: Longueurs d'énoncé à couvrir, en mots. À ~0,67 s par mot (durée moyenne des
#: enregistrements + pause), cela balaie ~2 s à ~9 s, soit la cible de 5–8 s
#: encadrée de part et d'autre. Les mots eux-mêmes ne sont **pas** codés en dur :
#: ils sont tirés de l'automate (cf. ``_sample_utterances``), donc valides par
#: construction — un énoncé hors grammaire serait introuvable par le décodeur et
#: l'écart mesuré ne dirait rien de la performance.
UTTERANCE_LENGTHS: list[tuple[str, int]] = [
    ("court_1", 3),
    ("court_2", 4),
    ("court_3", 5),
    ("moyen_1", 7),
    ("moyen_2", 8),
    ("moyen_3", 9),
    ("moyen_4", 10),
    ("long_1", 11),
    ("long_2", 12),
    ("long_3", 13),
]


def _sample_utterances(seed: int) -> dict[str, list[str]]:
    """Tire un énoncé valide par longueur cible, par marche aléatoire dans l'automate.

    Générer plutôt que coder en dur évite deux pièges : un énoncé écrit à la main
    peut être hors grammaire (l'automate des expressions est bien plus contraint
    que l'intuition), et une liste figée se périmerait silencieusement à la
    moindre évolution de la grammaire. Le tirage est **déterministe** (``seed``
    fixe) : le corpus reste reproductible d'une exécution à l'autre.
    """
    import random

    from zarma_numbers.grammar import load_expression_grammar

    grammar = load_expression_grammar()
    rng = random.Random(seed)
    chosen: dict[str, list[str]] = {}
    for name, target in UTTERANCE_LENGTHS:
        for _ in range(200_000):
            state, words = grammar.start, []
            while len(words) <= target:
                if len(words) == target and grammar.is_accepting(state):
                    break
                transitions = grammar.transitions(state)
                if not transitions:
                    break
                word = rng.choice(sorted(transitions))
                words.append(word)
                state = transitions[word]
            if len(words) == target and grammar.is_accepting(state):
                chosen[name] = words
                break
        else:
            raise SystemExit(f"Aucun énoncé de {target} mots trouvé pour {name}.")
    return chosen


#: Pause insérée entre deux mots (secondes). Une valeur nulle collerait les mots
#: en un continuum irréaliste ; une valeur trop grande gonflerait artificiellement
#: la durée (donc le coût du modèle, qui est linéaire en trames).
INTER_WORD_GAP_S = 0.08


def _read_word(name: str) -> np.ndarray:
    path = WORDS_DIR / f"{name}.wav"
    with wave.open(str(path), "rb") as reader:
        if reader.getframerate() != SAMPLE_RATE or reader.getnchannels() != 1:
            raise SystemExit(f"{path} n'est pas du mono 16 kHz.")
        frames = reader.readframes(reader.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0


def _concat(words: list[str], gap_s: float = INTER_WORD_GAP_S) -> np.ndarray:
    gap = np.zeros(int(gap_s * SAMPLE_RATE), dtype=np.float32)
    parts: list[np.ndarray] = []
    for index, word in enumerate(words):
        if index:
            parts.append(gap)
        parts.append(_read_word(word))
    return np.concatenate(parts)


def _write(path: Path, samples: np.ndarray) -> float:
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(SAMPLE_RATE)
        writer.writeframes(pcm.tobytes())
    return len(samples) / SAMPLE_RATE


def _validate(words: list[str]) -> None:
    """Refuse un énoncé que la grammaire ne peut pas produire."""
    from zarma_numbers.grammar import load_expression_grammar

    grammar = load_expression_grammar()
    state = grammar.start
    for word in words:
        transitions = grammar.transitions(state)
        if word not in transitions:
            raise SystemExit(f"Énoncé hors grammaire : {' '.join(words)} (bloqué sur {word!r})")
        state = transitions[word]
    if not grammar.is_accepting(state):
        raise SystemExit(f"Énoncé non terminal : {' '.join(words)}")


def build(out_dir: Path, *, seed: int = 1234) -> list[dict[str, object]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    manifest: list[dict[str, object]] = []

    def record(name: str, samples: np.ndarray, expected: str, condition: str) -> None:
        duration = _write(out_dir / f"{name}.wav", samples)
        manifest.append(
            {
                "name": name,
                "file": f"{name}.wav",
                "expected_text": expected,
                "condition": condition,
                "duration_s": round(duration, 3),
            }
        )

    # 1) Énoncés propres, du court au long.
    utterances = _sample_utterances(seed)
    for name, words in utterances.items():
        _validate(words)
        record(name, _concat(words), " ".join(words), "propre")

    # 2) Bruit de fond additif à ~15 dB de RSB — un marché, pas un studio.
    base_words = utterances["moyen_3"]
    base = _concat(base_words)
    noise = rng.normal(0.0, 1.0, size=base.shape).astype(np.float32)
    rms_signal = float(np.sqrt(np.mean(base**2)))
    rms_noise = float(np.sqrt(np.mean(noise**2)))
    noise *= (rms_signal / rms_noise) * (10 ** (-15 / 20))
    record("bruit_15db", base + noise, " ".join(base_words), "bruit_15db")

    # 3) Silence de bord : le cas typique d'un appui manuel sur « enregistrer ».
    #    C'est la cible directe de l'élagage par VAD.
    pad = np.zeros(int(1.5 * SAMPLE_RATE), dtype=np.float32)
    record(
        "silences_bord",
        np.concatenate([pad, base, pad]),
        " ".join(base_words),
        "silences_bord",
    )

    # 4) Parole faible (−16 dB) : loin du micro.
    record("parole_faible", base * 0.15, " ".join(base_words), "parole_faible")

    # 5) Silence total : doit être détecté et rejeté, jamais transformé en nombre.
    record("silence_total", np.zeros(int(8.0 * SAMPLE_RATE), dtype=np.float32), "", "silence_total")

    # 6) Bruit seul, sans parole : même exigence de rejet que le silence.
    only_noise = rng.normal(0.0, 0.01, size=int(6.0 * SAMPLE_RATE)).astype(np.float32)
    record("bruit_seul", only_noise, "", "bruit_seul")

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPO / "dataset" / "benchmark" / "perf")
    args = parser.parse_args(argv)
    manifest = build(args.out)
    total = sum(float(entry["duration_s"]) for entry in manifest)
    print(f"{len(manifest)} énoncés écrits dans {args.out} ({total:.1f}s au total)")
    for entry in manifest:
        print(
            f"  {entry['name']:16s} {entry['duration_s']:5.2f}s  "
            f"{entry['condition']:14s} « {entry['expected_text']} »"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
