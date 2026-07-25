#!/usr/bin/env python
"""Prépare une séance d'enregistrement pour la banque vocale (story 6.1, task 6).

Un locuteur enregistre avec le matériel qu'il a : le résultat arrive rarement au
format exact attendu. Ce script fait le pont entre « ce qui a été enregistré » et
« ce que la banque sait lire », sans rien redemander au locuteur :

1. **conversion** au format canonique du projet — 16 kHz, mono, PCM 16 bits
   (mêmes briques que le pipeline de l'API : ``soundfile`` + ``soxr``) ;
2. **détourage des silences** de début et de fin — la consigne d'enregistrement
   promet « laisse 0,5 s de silence, je le couperai » ; c'est ici que c'est tenu.
   Sans ça, chaque mot traîne une pause et l'assemblage sonne haché ;
3. **correction des noms de fichier** évidents : ``igouwav.wav`` → ``igou.wav``
   (faute de frappe fréquente quand on tape l'extension deux fois) ;
4. **tri** entre mots composables, consignes entières, et tout le reste ;
5. **rapport** de ce qui manque encore, calculé depuis le lexique.

Ce qui n'est **jamais** fait ici :

- deviner à quel mot correspond un fichier au nom inconnu — il est signalé, pas
  renommé au jugé ;
- toucher aux fichiers source : la sortie va dans un répertoire distinct.

Usage
-----
    # Aperçu sans rien écrire
    uv run python scripts/speech/prepare_bank.py --source ~/Music/voix2 --dry-run

    # Préparer la banque
    uv run python scripts/speech/prepare_bank.py \
        --source ~/Music/voix2 --out dataset/voice/v4

    # Puis vérifier / écouter
    uv run python scripts/speech/say_number.py --voice v4 \
        --bank-dir dataset/voice/v4/words --prompt-dir dataset/voice/v4/prompts \
        --coverage
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr

_SPEECH_DIR = Path(__file__).resolve().parent
if str(_SPEECH_DIR) not in sys.path:
    sys.path.insert(0, str(_SPEECH_DIR))

from voice_bank import (  # noqa: E402
    REQUIRED_PROMPTS,
    TARGET_RATE,
    target_vocabulary,
    write_wav,
)
from zarma_numbers.loader import load_lexicon  # noqa: E402

#: Consignes reconnues : celles qu'exige le code, plus deux facultatives.
KNOWN_PROMPTS: tuple[str, ...] = (*REQUIRED_PROMPTS, "repeat", "result")

#: Silence conservé de part et d'autre du mot détouré (secondes).
#: Assez court pour ne pas hacher l'assemblage, assez long pour ne pas couper
#: une attaque ou une fin de syllabe.
TRIM_MARGIN_SECONDS = 0.03

#: Seuil de détourage, en dB **sous le pic** du fichier. Relatif et non absolu :
#: un seuil absolu dépendrait du gain du micro, donc du locuteur.
TRIM_THRESHOLD_DB = -40.0


@dataclass
class PreparationReport:
    """Ce qui a été fait, et ce qu'il reste à faire."""

    words: dict[str, Path] = field(default_factory=dict)
    prompts: dict[str, Path] = field(default_factory=dict)
    renamed: list[tuple[str, str]] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    missing_words: list[str] = field(default_factory=list)
    missing_prompts: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """La banque est-elle complète et sans échec de conversion ?"""
        return not self.missing_words and not self.missing_prompts and not self.failed


def load_mono(path: Path) -> tuple[np.ndarray, int]:
    """Lit un WAV en float32 mono (moyenne des canaux si nécessaire)."""
    samples, rate = sf.read(str(path), dtype="float32", always_2d=True)
    return samples.mean(axis=1), int(rate)


def trim_silence(
    samples: np.ndarray,
    rate: int,
    *,
    threshold_db: float = TRIM_THRESHOLD_DB,
    margin_seconds: float = TRIM_MARGIN_SECONDS,
) -> np.ndarray:
    """Retire les silences de tête et de queue, en gardant une petite marge.

    Le seuil est **relatif au pic** du fichier : un enregistrement fort et un
    enregistrement faible sont détourés au même endroit perceptif. Un fichier
    entièrement silencieux est renvoyé tel quel — le tronquer à zéro
    échangerait un problème visible contre un problème silencieux.
    """
    if samples.size == 0:
        return samples
    peak = float(np.max(np.abs(samples)))
    if peak <= 0.0:
        return samples

    threshold = peak * (10.0 ** (threshold_db / 20.0))
    loud = np.flatnonzero(np.abs(samples) >= threshold)
    if loud.size == 0:
        return samples

    margin = int(margin_seconds * rate)
    start = max(0, int(loud[0]) - margin)
    end = min(samples.size, int(loud[-1]) + margin + 1)
    return samples[start:end]


def to_canonical_pcm(samples: np.ndarray, rate: int) -> bytes:
    """Rééchantillonne en 16 kHz et encode en PCM 16 bits.

    ``soxr`` est le rééchantillonneur déjà employé par le pipeline audio de
    l'API : même traitement des deux côtés, donc pas d'écart de timbre entre ce
    que l'app entend et ce qu'elle prononce.
    """
    if rate != TARGET_RATE:
        samples = soxr.resample(samples, rate, TARGET_RATE)
    clipped = np.clip(samples, -1.0, 1.0)
    return (clipped * 32767.0).astype("<i2").tobytes()


def canonical_name(stem: str, vocabulary: set[str]) -> tuple[str, bool]:
    """Nom de mot corrigé, et si une correction a eu lieu.

    Deux corrections, toutes deux **justifiables**, jamais un rapprochement
    approximatif (NFR14) :

    1. le suffixe ``wav`` collé au mot (``igouwav`` → ``igou``), faute de frappe
       mécanique — et seulement si le mot obtenu existe vraiment au lexique ;
    2. une **variante linguistique** déclarée au lexique ramenée à sa forme
       canonique (``zongou`` → ``zangou``). Ce n'est pas une devinette : c'est la
       même table de variantes que celle du normaliseur. La banque est indexée
       par la forme que ``generate`` produit, donc c'est bien celle-là qu'il faut.

    Un nom qui ne relève ni de l'une ni de l'autre reste inchangé, et sera
    signalé comme inconnu plutôt que renommé au jugé.
    """
    if stem in vocabulary:
        return stem, False
    if stem.endswith("wav") and stem[:-3] in vocabulary:
        return stem[:-3], True

    canonical = load_lexicon().linguistic_variant_map().get(stem)
    if canonical is not None and canonical in vocabulary:
        return canonical, True
    return stem, False


def prepare(
    source: Path,
    out: Path | None,
    *,
    trim: bool = True,
    dry_run: bool = False,
) -> PreparationReport:
    """Convertit et trie le contenu de ``source``. N'écrit rien si ``dry_run``."""
    vocabulary = target_vocabulary()
    report = PreparationReport()

    words_dir = (out / "words") if out is not None else None
    prompts_dir = (out / "prompts") if out is not None else None

    for path in sorted(source.glob("*.wav")):
        stem = path.stem
        name, was_renamed = canonical_name(stem, vocabulary)

        if name in vocabulary:
            destination_dir, table = words_dir, report.words
        elif name in KNOWN_PROMPTS:
            destination_dir, table = prompts_dir, report.prompts
        else:
            report.unknown.append(path.name)
            continue

        try:
            samples, rate = load_mono(path)
            if trim:
                samples = trim_silence(samples, rate)
            pcm = to_canonical_pcm(samples, rate)
        except Exception as exc:  # audio illisible/corrompu : signalé, jamais ignoré
            report.failed.append((path.name, str(exc)))
            continue

        if was_renamed:
            report.renamed.append((path.name, f"{name}.wav"))

        destination = path if destination_dir is None else destination_dir / f"{name}.wav"
        if not dry_run and destination_dir is not None:
            write_wav(destination, pcm)
        table[name] = destination

    report.missing_words = sorted(vocabulary - set(report.words))
    report.missing_prompts = [p for p in REQUIRED_PROMPTS if p not in report.prompts]
    return report


def print_report(report: PreparationReport, *, source: Path) -> None:
    print(f"Source : {source}")
    print(f"  {len(report.words)} mot(s) et {len(report.prompts)} consigne(s) préparés.")

    if report.renamed:
        print(f"\n  {len(report.renamed)} nom(s) de fichier corrigé(s) :")
        for before, after in report.renamed:
            print(f"    {before} → {after}")

    if report.failed:
        print(f"\n  ⛔ {len(report.failed)} fichier(s) illisible(s) :")
        for name, reason in report.failed:
            print(f"    {name} : {reason}")

    if report.unknown:
        print(f"\n  {len(report.unknown)} fichier(s) hors banque vocale (ignorés) :")
        for name in report.unknown:
            print(f"    {name}")
        print("    → s'il s'agit du corpus de contrôle (groupe E3), il a sa propre place.")

    if report.missing_words:
        print(f"\n  {len(report.missing_words)} mot(s) encore manquant(s) :")
        for word in report.missing_words:
            print(f"    - {word}")
    if report.missing_prompts:
        print(f"\n  {len(report.missing_prompts)} consigne(s) encore manquante(s) :")
        for name in report.missing_prompts:
            print(f"    - {name}")

    if report.ok:
        print("\n  ✅ Banque complète.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prépare une banque vocale enregistrée.")
    parser.add_argument("--source", type=Path, required=True, help="Répertoire des prises brutes.")
    parser.add_argument("--out", type=Path, default=None, help="Répertoire de sortie préparé.")
    parser.add_argument("--dry-run", action="store_true", help="N'écrit rien ; affiche le bilan.")
    parser.add_argument("--no-trim", action="store_true", help="Conserve les silences.")
    args = parser.parse_args(argv)

    source = args.source.expanduser()
    if not source.is_dir():
        print(f"⛔ Répertoire introuvable : {source}", file=sys.stderr)
        return 2
    if args.out is None and not args.dry_run:
        parser.error("--out est requis (ou --dry-run pour un simple bilan)")

    report = prepare(
        source,
        None if args.dry_run else args.out.expanduser(),
        trim=not args.no_trim,
        dry_run=args.dry_run,
    )
    print_report(report, source=source)
    if not args.dry_run:
        print(f"\nÉcrit dans : {args.out.expanduser()}")
    return 0 if not report.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
