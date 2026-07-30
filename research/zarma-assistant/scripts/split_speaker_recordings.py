"""Découpe automatiquement les longs enregistrements (un fichier par
locuteur, 59 phrases dites à la suite avec quelques secondes de pause entre
chaque) en 59 fichiers individuels, nommés d'après le nombre réellement
prononcé (colonne `nombre` de asr_recording_prompts.csv, dans l'ordre).

Détection des pauses par silence (pydub, s'appuie sur ffmpeg — `brew install
ffmpeg` si besoin). Comme les locuteurs ont enregistré dans l'ordre du CSV,
le Nième segment détecté correspond à la Nième ligne du CSV.

Chaque locuteur parle à un volume et un rythme différents — un seuil de
silence fixe ne convient donc pas à tout le monde (vérifié empiriquement :
avec des réglages fixes, les 8 premiers locuteurs testés donnaient entre 1 et
78 segments détectés au lieu de 59). Le script recherche donc, **pour chaque
fichier séparément**, la combinaison (durée de pause minimale, seuil de
silence) qui tombe exactement sur le nombre de phrases attendu, plutôt que
d'utiliser des valeurs uniques pour tout le monde.

**Sécurité** : si aucune combinaison testée ne tombe exactement sur le compte
attendu, le script n'essaie PAS de deviner un étiquetage — il exporte le
meilleur résultat approché (numéroté, sans les vrais noms) dans un dossier
"a_verifier/" et affiche l'écart, plutôt que de risquer un mauvais
étiquetage silencieux (bien pire qu'un export manuel à corriger).

Usage :
  uv run python scripts/split_speaker_recordings.py /Users/pc/Music/2voix
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from pydub import AudioSegment
from pydub.silence import detect_nonsilent

PROMPTS_CSV = Path(__file__).resolve().parent.parent / "data" / "asr_recording_prompts.csv"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "asr_speakers"
TARGET_SAMPLE_RATE = 16_000

AUDIO_EXTENSIONS = {".m4a", ".mp3", ".wav", ".opus", ".ogg", ".flac"}


def _load_expected_numbers() -> list[str]:
    with PROMPTS_CSV.open(encoding="utf-8") as f:
        return [row["nombre"] for row in csv.DictReader(f)]


#: Grille de recherche : durées de pause minimale (ms) et décalages de seuil
#: de silence (dB en dessous du dBFS moyen du fichier) essayés pour chaque
#: locuteur, jusqu'à tomber exactement sur le nombre de phrases attendu.
_MIN_SILENCE_GRID = (300, 400, 500, 600, 700, 800, 900, 1000, 1200, 1500, 1800)
_SILENCE_OFFSET_GRID = (6, 8, 10, 12, 14, 16, 18, 20, 22, 25, 28, 32, 36, 40)


def _search_params(
    audio: AudioSegment, expected_count: int
) -> tuple[list[tuple[int, int]], tuple[int, float], int]:
    """Cherche la combinaison (pause min, seuil) qui tombe exactement sur
    `expected_count` segments. Retourne (segments, params_utilisés, écart) —
    écart = 0 si un match exact a été trouvé, sinon celui du meilleur essai."""
    best: tuple[int, list[tuple[int, int]], tuple[int, float]] | None = None
    for min_silence_len in _MIN_SILENCE_GRID:
        for offset in _SILENCE_OFFSET_GRID:
            silence_thresh = audio.dBFS - offset
            segments = detect_nonsilent(
                audio, min_silence_len=min_silence_len, silence_thresh=silence_thresh
            )
            diff = abs(len(segments) - expected_count)
            if diff == 0:
                return segments, (min_silence_len, silence_thresh), 0
            if best is None or diff < best[0]:
                best = (diff, segments, (min_silence_len, silence_thresh))
    assert best is not None
    return best[1], best[2], best[0]


def _split_one(
    audio_path: Path,
    expected_numbers: list[str],
    padding_ms: int,
) -> None:
    speaker = audio_path.stem
    print(f"\n=== {speaker} ({audio_path.name}) ===")

    audio = AudioSegment.from_file(audio_path)
    audio = audio.set_channels(1).set_frame_rate(TARGET_SAMPLE_RATE)

    segments, (min_silence_len, silence_thresh), diff = _search_params(
        audio, len(expected_numbers)
    )

    print(
        f"  {len(segments)} segment(s) trouvé(s) (attendu : {len(expected_numbers)}) "
        f"avec pause min {min_silence_len} ms, seuil {silence_thresh:.1f} dBFS"
        + (" — match exact." if diff == 0 else f" — écart de {diff}, aucun réglage exact trouvé.")
    )

    if diff == 0:
        out_dir = OUTPUT_DIR / speaker
        out_dir.mkdir(parents=True, exist_ok=True)
        for (start, end), number in zip(segments, expected_numbers, strict=True):
            start = max(0, start - padding_ms)
            end = min(len(audio), end + padding_ms)
            clip = audio[start:end]
            clip.export(out_dir / f"{number}.wav", format="wav")
        print(f"  OK -> {out_dir} ({len(segments)} fichiers)")
    else:
        out_dir = OUTPUT_DIR / "a_verifier" / speaker
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, (start, end) in enumerate(segments):
            start = max(0, start - padding_ms)
            end = min(len(audio), end + padding_ms)
            clip = audio[start:end]
            clip.export(out_dir / f"segment_{i:03d}.wav", format="wav")
        print(
            f"  ATTENTION : aucune combinaison testée ne tombe exactement sur "
            f"{len(expected_numbers)} segments (meilleur essai : {len(segments)}, écart {diff}). "
            f"Meilleur résultat approché exporté sans renommage dans {out_dir} pour "
            f"vérification/découpage manuel."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings_dir", type=Path, help="Dossier contenant un fichier par locuteur")
    parser.add_argument(
        "--padding-ms",
        type=int,
        default=120,
        help="Marge ajoutée avant/après chaque segment détecté, pour ne pas couper le début/la fin d'un mot (défaut 120).",
    )
    args = parser.parse_args()

    expected_numbers = _load_expected_numbers()
    audio_files = sorted(
        p for p in args.recordings_dir.glob("*") if p.suffix.lower() in AUDIO_EXTENSIONS
    )
    if not audio_files:
        raise SystemExit(f"Aucun fichier audio trouvé dans {args.recordings_dir}")

    print(f"{len(audio_files)} fichier(s) locuteur trouvé(s), {len(expected_numbers)} phrases attendues chacun.")

    for audio_path in audio_files:
        _split_one(audio_path, expected_numbers, padding_ms=args.padding_ms)

    print(f"\nTerminé. Résultats dans {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
