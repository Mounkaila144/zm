"""Restitution vocale zarma par concaténation — cœur réutilisable (story 6.1, task 6).

L'utilisateur cible **ne lit pas**. Afficher « 38 » ne suffit donc pas : le
résultat doit être *dit*. Le vocabulaire des nombres étant **fermé (33 mots)**,
prononcer n'importe quel résultat ne demande aucune synthèse vocale entraînée —
seulement une banque de mots enregistrés, assemblés dans l'ordre. C'est la
décision D3 de la story, prototypée en 5.6 et généralisée ici.

Ce module porte la logique (testable, sans audio réel) ; ``say_number.py`` n'est
plus que sa ligne de commande.

Ce qui peut être prononcé
-------------------------

===================== ===================================================
Énoncé                Composition
===================== ===================================================
Un nombre             ``generate(n)``
Une expression        ``render_expression(expr)`` — pour la relecture
Un résultat           ``render_result(result)``, reste de division compris
Une confirmation      consigne enregistrée + l'énoncé à confirmer
Un refus              consigne enregistrée seule (hors domaine, FR21)
===================== ===================================================

Les **consignes** (« c'est bien … ? », « je ne peux pas répondre ») ne sont pas
composables : ce sont des phrases entières, qu'un locuteur natif enregistre une
fois par voix. Le code ne les fabrique pas — pas plus qu'il n'invente un mot
zarma ailleurs dans ce projet.

Deux règles
-----------

- **Fail-closed (FR21).** Si un seul segment manque, **rien** n'est produit :
  ``VoiceBankError``. Prononcer un nombre à moitié serait indétectable pour un
  utilisateur qui ne lit pas — donc pire que le silence.
- **Source unique.** Les formes viennent de ``zarma_numbers`` (``generate``,
  ``render_result``) ; aucune n'est réécrite ici.

Fonctionnement **hors ligne** : lecture de fichiers WAV locaux, aucun réseau,
aucun modèle.
"""

from __future__ import annotations

import glob
import os
import re
import wave
from dataclasses import dataclass
from pathlib import Path

from zarma_numbers.expressions import Expression, ExpressionResult, render_expression, render_result
from zarma_numbers.generator import generate
from zarma_numbers.loader import load_lexicon

#: Répertoires fouillés pour construire la banque à partir des nombres enregistrés.
DEFAULT_SOURCES = ("~/Music/v1", "~/Music/v2", "~/Music/v3")

#: Silence inséré entre deux segments (secondes) — respiration naturelle.
WORD_GAP_SECONDS = 0.06

#: Format audio canonique du projet (identique à la capture mobile, FR1).
TARGET_RATE = 16_000
TARGET_CHANNELS = 1
TARGET_WIDTH = 2

#: Nature d'un segment : un mot composable, ou une consigne enregistrée entière.
WORD = "word"
PROMPT = "prompt"

#: Consignes attendues dans la banque (une par voix), avec leur rôle.
PROMPT_CONFIRM = "confirm"
PROMPT_CANNOT_ANSWER = "cannot_answer"
REQUIRED_PROMPTS: tuple[str, ...] = (PROMPT_CONFIRM, PROMPT_CANNOT_ANSWER)

#: Un segment à prononcer : ``(nature, clé)``.
Segment = tuple[str, str]


class VoiceBankError(Exception):
    """Erreur contrôlée de la banque vocale (segment manquant, audio illisible)."""


# --------------------------------------------------------------------------- #
# Ce qu'il faut prononcer (composé depuis zarma_numbers, jamais réécrit)
# --------------------------------------------------------------------------- #


def _words(form: str) -> tuple[Segment, ...]:
    return tuple((WORD, word) for word in form.split())


def number_utterance(value: int) -> tuple[Segment, ...]:
    """Segments prononçant le nombre ``value``."""
    return _words(generate(value))


def expression_utterance(expression: Expression) -> tuple[Segment, ...]:
    """Segments relisant l'opération entendue (« vingt-trois plus quinze »)."""
    return _words(render_expression(expression))


def result_utterance(result: ExpressionResult) -> tuple[Segment, ...]:
    """Segments prononçant le résultat — reste de division inclus (``ga cindi``)."""
    return _words(render_result(result))


def confirmation_utterance(utterance: tuple[Segment, ...]) -> tuple[Segment, ...]:
    """Consigne de confirmation suivie de l'énoncé à confirmer.

    C'est le point que la story identifie comme bloquant : la confirmation
    affichée à l'écran (« C'est bien 42 ? ») est inopérante pour la cible, alors
    qu'elle est le chemin nominal — 87,5 % des reconnaissances en 5.6. La même
    modalité vocale la rend utilisable.
    """
    return ((PROMPT, PROMPT_CONFIRM), *utterance)


def refusal_utterance() -> tuple[Segment, ...]:
    """Consigne annonçant qu'aucune réponse n'est possible (résultat hors domaine).

    Un refus **doit** être audible : rester silencieux serait indistinguable
    d'une panne pour l'utilisateur (AC4/FR21).
    """
    return ((PROMPT, PROMPT_CANNOT_ANSWER),)


# --------------------------------------------------------------------------- #
# Banque vocale
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class VoiceBank:
    """Fichiers audio disponibles pour une voix : mots composables + consignes."""

    voice: str
    words: dict[str, Path]
    prompts: dict[str, Path]

    def path_for(self, segment: Segment) -> Path | None:
        kind, key = segment
        table = self.prompts if kind == PROMPT else self.words
        return table.get(key)

    def missing(self, utterance: tuple[Segment, ...]) -> list[Segment]:
        """Segments absents de la banque, dans l'ordre, sans doublon."""
        absent: list[Segment] = []
        for segment in utterance:
            if self.path_for(segment) is None and segment not in absent:
                absent.append(segment)
        return absent

    def can_say(self, utterance: tuple[Segment, ...]) -> bool:
        return not self.missing(utterance)


def build_bank(
    voice: str,
    sources: tuple[str, ...] = DEFAULT_SOURCES,
    word_dir: Path | None = None,
    prompt_dir: Path | None = None,
) -> VoiceBank:
    """Assemble la banque d'une voix.

    Trois origines, dans cet ordre de priorité croissante :

    1. les **nombres déjà enregistrés** (``v<N>-<nombre>.wav``) dont la forme
       canonique tient en un seul mot — récupération gratuite de l'existant ;
    2. les mots enregistrés à l'unité dans ``word_dir`` (``<mot>.wav``) ;
    3. les consignes entières de ``prompt_dir`` (``<nom>.wav``).
    """
    words: dict[str, Path] = {}
    for source in sources:
        directory = Path(os.path.expanduser(source))
        if directory.name != voice or not directory.is_dir():
            continue
        for path in sorted(glob.glob(str(directory / "*.wav"))):
            match = re.fullmatch(rf"{re.escape(voice)}-(\d+)\.wav", os.path.basename(path))
            if not match:
                continue
            try:
                form = generate(int(match.group(1)))
            except Exception:  # forme non résolue / hors plage : ignorée, jamais devinée
                continue
            if len(form.split()) == 1:  # un fichier = exactement un mot
                words[form] = Path(path)

    if word_dir is not None and word_dir.is_dir():
        for path in sorted(glob.glob(str(word_dir / "*.wav"))):
            words[Path(path).stem] = Path(path)

    prompts: dict[str, Path] = {}
    if prompt_dir is not None and prompt_dir.is_dir():
        for path in sorted(glob.glob(str(prompt_dir / "*.wav"))):
            prompts[Path(path).stem] = Path(path)

    return VoiceBank(voice=voice, words=words, prompts=prompts)


# --------------------------------------------------------------------------- #
# Assemblage audio
# --------------------------------------------------------------------------- #


def read_pcm(path: Path) -> bytes:
    """Lit un WAV canonique (mono 16 kHz PCM16) et retourne ses échantillons.

    Le format est **vérifié**, pas converti : un rééchantillonnage silencieux
    dégraderait l'intelligibilité sans que personne le sache.
    """
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


def _silence(seconds: float) -> bytes:
    return b"\x00" * (int(seconds * TARGET_RATE) * TARGET_WIDTH)


def synthesize(
    utterance: tuple[Segment, ...], bank: VoiceBank, *, gap_seconds: float = WORD_GAP_SECONDS
) -> bytes:
    """Assemble le PCM de ``utterance``. **Rien** n'est produit s'il manque un segment.

    :raises VoiceBankError: si l'énoncé est vide, ou si un segment manque à la
        banque — le silence total est la seule alternative sûre à un énoncé
        tronqué (FR21).
    """
    if not utterance:
        raise VoiceBankError("énoncé vide : rien à prononcer.")

    absent = bank.missing(utterance)
    if absent:
        rendered = ", ".join(f"{kind}:{key}" for kind, key in absent)
        raise VoiceBankError(f"segments absents de la banque « {bank.voice} » : {rendered}")

    gap = _silence(gap_seconds)
    chunks: list[bytes] = []
    for index, segment in enumerate(utterance):
        if index:
            chunks.append(gap)
        path = bank.path_for(segment)
        assert path is not None  # garanti par le contrôle d'absence ci-dessus
        chunks.append(read_pcm(path))
    return b"".join(chunks)


def write_wav(path: Path, pcm: bytes) -> None:
    """Écrit du PCM canonique dans un WAV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(TARGET_CHANNELS)
        writer.setsampwidth(TARGET_WIDTH)
        writer.setframerate(TARGET_RATE)
        writer.writeframes(pcm)


def duration_seconds(pcm: bytes) -> float:
    return len(pcm) / (TARGET_RATE * TARGET_WIDTH)


# --------------------------------------------------------------------------- #
# Couverture : que reste-t-il à enregistrer ?
# --------------------------------------------------------------------------- #


def target_vocabulary() -> set[str]:
    """Mots distincts nécessaires pour prononcer nombres, résultats **et opérations**.

    Balaie 0–1000 puis des valeurs sentinelles couvrant les échelles supérieures
    (milliers, ``dala``, million) — la grammaire étant compositionnelle, cela
    suffit à énumérer le vocabulaire complet. S'y ajoutent :

    - le marqueur de reste de division (``ga``), sans lequel aucun résultat de
      division non entière n'est prononçable ;
    - les **mots d'opérateur résolus** au lexique, sans lesquels l'application ne
      peut pas relire l'opération entendue — or c'est exactement ce qu'exige la
      confirmation, qui est le chemin nominal (87,5 % des reconnaissances en
      5.6). Un opérateur non résolu est absent d'ici : on n'enregistre pas un mot
      qu'aucun locuteur n'a validé.
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
            words.update(generate(value).split())
        except Exception:  # forme non résolue dans le lexique — ignorée ici
            continue

    # Le reste de division emprunte un marqueur absent des nombres : il faut
    # l'enregistrer aussi, sinon « 20 reste 3 » reste indicible.
    words.update(render_result(_remainder_probe()).split())

    # Les mots d'opérateur : ils ne sortent jamais de ``generate``, mais la
    # relecture d'une opération en a besoin.
    for operator in load_lexicon().operators.values():
        if operator.canonical is not None:
            words.update(operator.canonical.split())
    return words


def _remainder_probe() -> ExpressionResult:
    """Un résultat de division avec reste, servant de sonde de vocabulaire."""
    return ExpressionResult(expression=Expression(103, "/", 5), value=20, remainder=3)


def missing_vocabulary(bank: VoiceBank) -> list[str]:
    """Mots du vocabulaire cible absents de la banque (à faire enregistrer)."""
    return sorted(target_vocabulary() - set(bank.words))


def missing_prompts(bank: VoiceBank) -> list[str]:
    """Consignes attendues absentes de la banque."""
    return [name for name in REQUIRED_PROMPTS if name not in bank.prompts]


def number_coverage(bank: VoiceBank, upper: int = 1000) -> tuple[int, int]:
    """(prononçables, total) sur ``0..upper`` — mesure honnête de la couverture."""
    total = upper + 1
    ok = 0
    for value in range(total):
        try:
            utterance = number_utterance(value)
        except Exception:  # forme non résolue : non prononçable, comptée comme telle
            continue
        if bank.can_say(utterance):
            ok += 1
    return ok, total


__all__ = [
    "DEFAULT_SOURCES",
    "PROMPT",
    "PROMPT_CANNOT_ANSWER",
    "PROMPT_CONFIRM",
    "REQUIRED_PROMPTS",
    "TARGET_RATE",
    "WORD",
    "Segment",
    "VoiceBank",
    "VoiceBankError",
    "build_bank",
    "confirmation_utterance",
    "duration_seconds",
    "expression_utterance",
    "missing_prompts",
    "missing_vocabulary",
    "number_coverage",
    "number_utterance",
    "read_pcm",
    "refusal_utterance",
    "result_utterance",
    "synthesize",
    "target_vocabulary",
    "write_wav",
]
