#!/usr/bin/env python
"""PROTOTYPE — restitution vocale d'un nombre zarma par concaténation (story 6.1, task 6).

Le vocabulaire des nombres est **fermé (33 mots)** : dire n'importe quel nombre de
0 à 1 000 000 ne demande donc pas de synthèse vocale entraînée, seulement une
**banque de mots enregistrés** assemblés dans l'ordre.

Principe
--------
1. ``zarma_numbers.generate(n)`` donne la forme canonique — **source unique**,
   jamais réécrite ici.
2. Chaque mot de cette forme est cherché dans la banque vocale.
3. Les extraits sont concaténés, séparés d'un court silence, et écrits en WAV.

**Fail-closed** (FR21) : si un seul mot manque, **rien n'est produit**. Prononcer
un nombre à moitié serait pire que se taire — l'utilisateur cible ne lit pas et
n'aurait aucun moyen de détecter la troncature.

Banque vocale
-------------
Construite automatiquement depuis les enregistrements existants : tout fichier
``v<N>-<nombre>.wav`` dont la forme canonique tient en **un seul mot** devient
une entrée de banque (ex. ``v1-20.wav`` → ``waranka``).

Les mots restants (formes combinées, connecteurs, échelles) doivent être
enregistrés séparément et déposés dans le répertoire de banque sous le nom
``<mot>.wav`` — voir ``--list-missing``.

Usage
-----
    # Que manque-t-il pour couvrir 0–1 000 000 ?
    uv run python scripts/speech/say_number.py --voice v1 --list-missing

    # Prononcer un nombre
    uv run python scripts/speech/say_number.py --voice v1 --number 20 --out /tmp/20.wav
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import wave
from pathlib import Path

import zarma_numbers

#: Répertoires fouillés pour construire la banque à partir des nombres enregistrés.
DEFAULT_SOURCES = ("~/Music/v1", "~/Music/v2", "~/Music/v3")

#: Silence inséré entre deux mots (secondes) — respiration naturelle.
WORD_GAP_SECONDS = 0.06

TARGET_RATE = 16_000
TARGET_CHANNELS = 1
TARGET_WIDTH = 2


class VoiceBankError(Exception):
    """Erreur contrôlée de la banque vocale (mot manquant, audio illisible)."""


def target_vocabulary() -> set[str]:
    """Ensemble des mots distincts nécessaires pour dire n'importe quel nombre.

    Balaie 0–1000 puis des valeurs sentinelles couvrant les échelles supérieures
    (milliers, ``dala``, million) — la grammaire étant compositionnelle, cela
    suffit à énumérer le vocabulaire complet.
    """

    probes = list(range(0, 1001)) + [
        2_000,
        5_000,
        10_000,
        12_345,
        100_000,
        100_005,
        500_000,
        999_999,
        1_000_000,
    ]
    words: set[str] = set()
    for value in probes:
        try:
            words.update(zarma_numbers.generate(value).split())
        except Exception:  # forme non résolue dans le lexique — ignorée ici
            continue
    return words


def build_bank(voice: str, sources: tuple[str, ...], extra_dir: Path | None) -> dict[str, Path]:
    """Construit la banque ``mot -> fichier`` pour une voix donnée.

    Deux origines, la seconde primant : les nombres déjà enregistrés dont la
    forme tient en un mot, puis les fichiers ``<mot>.wav`` du répertoire dédié.
    """

    bank: dict[str, Path] = {}
    for source in sources:
        directory = Path(os.path.expanduser(source))
        if directory.name != voice or not directory.is_dir():
            continue
        for path in glob.glob(str(directory / "*.wav")):
            match = re.fullmatch(rf"{voice}-(\d+)\.wav", os.path.basename(path))
            if not match:
                continue
            try:
                form = zarma_numbers.generate(int(match.group(1)))
            except Exception:
                continue
            if len(form.split()) == 1:  # un fichier = exactement un mot
                bank[form] = Path(path)

    if extra_dir is not None and extra_dir.is_dir():
        for path in glob.glob(str(extra_dir / "*.wav")):
            bank[Path(path).stem] = Path(path)
    return bank


def _read_pcm(path: Path) -> bytes:
    """Lit un WAV canonique (mono 16 kHz PCM16) et retourne ses échantillons."""

    try:
        with wave.open(str(path), "rb") as reader:
            if (
                reader.getnchannels() != TARGET_CHANNELS
                or reader.getframerate() != TARGET_RATE
                or reader.getsampwidth() != TARGET_WIDTH
            ):
                raise VoiceBankError(f"format non canonique : {path.name}")
            return reader.readframes(reader.getnframes())
    except wave.Error as exc:
        raise VoiceBankError(f"audio illisible : {path.name}") from exc


def say(number: int, bank: dict[str, Path]) -> tuple[bytes, str]:
    """Assemble l'audio prononçant ``number``. Lève si un mot manque (fail-closed)."""

    form = zarma_numbers.generate(number)
    words = form.split()
    missing = [word for word in words if word not in bank]
    if missing:
        raise VoiceBankError(
            f"mots absents de la banque : {', '.join(sorted(set(missing)))} "
            f"(forme demandée : « {form} »)"
        )

    silence = b"\x00" * int(WORD_GAP_SECONDS * TARGET_RATE) * TARGET_WIDTH
    chunks: list[bytes] = []
    for index, word in enumerate(words):
        if index:
            chunks.append(silence)
        chunks.append(_read_pcm(bank[word]))
    return b"".join(chunks), form


def write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(TARGET_CHANNELS)
        writer.setsampwidth(TARGET_WIDTH)
        writer.setframerate(TARGET_RATE)
        writer.writeframes(pcm)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prononce un nombre zarma par concaténation.")
    parser.add_argument("--voice", default="v1", help="Locuteur (v1, v2, v3…).")
    parser.add_argument("--number", type=int, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--bank-dir", type=Path, default=None, help="Mots enregistrés à l'unité.")
    parser.add_argument("--list-missing", action="store_true")
    parser.add_argument("--coverage", action="store_true", help="Combien de nombres 0–1000 ?")
    args = parser.parse_args(argv)

    bank = build_bank(args.voice, DEFAULT_SOURCES, args.bank_dir)
    print(f"Banque « {args.voice} » : {len(bank)} mot(s) disponible(s).")

    if args.list_missing:
        missing = sorted(target_vocabulary() - set(bank))
        print(f"\n{len(missing)} mot(s) à enregistrer (déposer en <mot>.wav dans --bank-dir) :")
        for word in missing:
            print(f"  - {word}")
        return 0

    if args.coverage:
        ok = sum(
            1
            for value in range(0, 1001)
            if all(w in bank for w in zarma_numbers.generate(value).split())
        )
        print(f"Couverture : {ok}/1001 nombres de 0 à 1000 prononçables.")
        return 0

    if args.number is None:
        parser.error("--number est requis (ou --list-missing / --coverage)")

    try:
        pcm, form = say(args.number, bank)
    except VoiceBankError as exc:
        print(f"⛔ {exc}", flush=True)
        return 1

    duration = len(pcm) / (TARGET_RATE * TARGET_WIDTH)
    print(f"{args.number} → « {form} »  ({duration:.2f}s)")
    if args.out:
        write_wav(args.out, pcm)
        print(f"écrit : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
