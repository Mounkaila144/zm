"""Génération déterministe et fail-closed du manifest dataset (story 4.5).

Le manifest est un artefact **dérivé** et versionné (JSONL) : il ne contient ni
``anon_id``, ni ``device_info``, ni chemin absolu, ni audio brut — uniquement une
référence audio opaque relative, le nombre attendu, la clé locuteur (déjà non
réversible), la région éventuelle et le split.

Garanties :
- **Prédicat unique** d'éligibilité (``status = validated AND audio_ref
  IS NOT NULL``) via :meth:`ContributionRepo.dataset_manifest_rows`.
- **Fail-closed** : par défaut, la moindre entrée invalide (audio absent,
  illisible, non canonique, métadonnée manquante) empêche toute écriture ; aucun
  manifest partiel n'est publié. ``allow_partial`` permet d'exclure explicitement
  les entrées invalides.
- **Split par locuteur** reproductible par seed : un ``speaker_key`` ne peut
  apparaître que dans un seul split.
- **Écriture atomique** : fichier temporaire puis ``os.replace``.
"""

from __future__ import annotations

import hashlib
import json
import os
import wave
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import ContributionRepo, DatasetManifestRow
from app.pipeline.audio import (
    TARGET_CHANNELS,
    TARGET_SAMPLE_RATE,
    TARGET_SAMPLE_WIDTH,
)
from app.storage.audio_store import AudioStorageError, FilesystemAudioStore

#: Seed par défaut du split par locuteur (documentée, versionnée avec le code).
DEFAULT_SPLIT_SEED = "zarma-dataset-split-v1"

#: Répartition par défaut, groupée par ``speaker_key`` (somme = 1.0).
DEFAULT_SPLITS: tuple[tuple[str, float], ...] = (
    ("train", 0.8),
    ("dev", 0.1),
    ("test", 0.1),
)

_SPLIT_TOLERANCE = 1e-9


@dataclass(frozen=True, slots=True)
class ManifestError:
    """Motif opaque d'exclusion d'un candidat (id UUID seul, aucune PII)."""

    contribution_id: UUID
    reason: str


@dataclass(frozen=True, slots=True)
class ManifestResult:
    """Compte-rendu de génération, sûr à journaliser."""

    written: bool
    output_path: Path | None
    entries: list[dict[str, object]]
    errors: list[ManifestError]
    seed: str

    @property
    def summary(self) -> str:
        if self.written:
            counts: dict[str, int] = {}
            for entry in self.entries:
                counts[str(entry["split"])] = counts.get(str(entry["split"]), 0) + 1
            per_split = ", ".join(f"{name}={counts[name]}" for name in sorted(counts))
            return (
                f"Manifest écrit : {len(self.entries)} entrée(s) [{per_split}] "
                f"(seed={self.seed})."
            )
        detail = f" ; {len(self.errors)} entrée(s) invalide(s)" if self.errors else ""
        return f"Manifest NON écrit (fail-closed){detail}."


def assign_split(
    speaker_key: str,
    seed: str = DEFAULT_SPLIT_SEED,
    splits: Sequence[tuple[str, float]] = DEFAULT_SPLITS,
) -> str:
    """Affecte un ``speaker_key`` à un split unique, de façon déterministe.

    L'affectation ne dépend que de ``(seed, speaker_key)`` : ajouter de nouveaux
    locuteurs ne déplace jamais les existants, et un même locuteur tombe toujours
    dans le même split.
    """

    digest = hashlib.sha256(f"{seed}:{speaker_key}".encode()).digest()
    fraction = int.from_bytes(digest[:8], "big") / 2**64
    cumulative = 0.0
    for name, ratio in splits:
        cumulative += ratio
        if fraction < cumulative:
            return name
    return splits[-1][0]


def _validate_splits(splits: Sequence[tuple[str, float]]) -> None:
    if not splits:
        raise ValueError("at least one split is required")
    names = [name for name, _ in splits]
    if len(set(names)) != len(names):
        raise ValueError("split names must be unique")
    if any(ratio < 0 for _, ratio in splits):
        raise ValueError("split ratios must be non-negative")
    total = sum(ratio for _, ratio in splits)
    if abs(total - 1.0) > _SPLIT_TOLERANCE:
        raise ValueError(f"split ratios must sum to 1.0 (got {total})")


def _verify_metadata(row: DatasetManifestRow) -> str | None:
    if not row.audio_ref:
        return "audio_ref_missing"
    if not row.speaker_key:
        return "speaker_key_missing"
    if row.expected_number is None or not (0 <= row.expected_number <= 1_000_000):
        return "expected_number_invalid"
    return None


def _verify_audio(store: FilesystemAudioStore, audio_ref: str) -> str | None:
    """Vérifie existence, lisibilité et format canonique (WAV mono 16 kHz PCM16)."""

    try:
        path = store.local_path(audio_ref)
    except AudioStorageError:
        return "audio_reference_invalid"
    if not path.is_file():
        return "audio_missing"
    try:
        with wave.open(str(path), "rb") as reader:
            if (
                reader.getnchannels() != TARGET_CHANNELS
                or reader.getframerate() != TARGET_SAMPLE_RATE
                or reader.getsampwidth() != TARGET_SAMPLE_WIDTH
                or reader.getnframes() == 0
            ):
                return "audio_not_canonical"
    except (wave.Error, OSError, EOFError):
        return "audio_unreadable"
    return None


def _entry(row: DatasetManifestRow, split: str) -> dict[str, object]:
    """Construit une entrée manifest dans un ordre de clés stable et sûr."""

    return {
        "audio_path": row.audio_ref,  # référence opaque relative (jamais absolue)
        "expected_number": row.expected_number,
        "speaker_key": row.speaker_key,
        "region": row.region,  # None si inconnue
        "split": split,
    }


def _atomic_write_jsonl(output_path: Path, entries: list[dict[str, object]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.parent / f".{output_path.name}.{uuid4().hex}.tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=False))
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output_path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


async def build_manifest(
    *,
    session: AsyncSession,
    audio_root: Path,
    output_path: Path,
    splits: Sequence[tuple[str, float]] = DEFAULT_SPLITS,
    seed: str = DEFAULT_SPLIT_SEED,
    allow_partial: bool = False,
) -> ManifestResult:
    """Sélectionne, vérifie, affecte les splits et écrit le manifest atomiquement.

    Les candidats sont lus dans une seule transaction cohérente (snapshot) via le
    prédicat unique d'éligibilité, ce qui évite les courses revue/retrait. Aucune
    entrée invalide n'est publiée ; sans ``allow_partial``, la présence d'au moins
    une entrée invalide bloque toute écriture (fail-closed).
    """

    _validate_splits(splits)
    store = FilesystemAudioStore(audio_root)
    rows = await ContributionRepo(session).dataset_manifest_rows()

    valid: list[DatasetManifestRow] = []
    errors: list[ManifestError] = []
    for row in rows:
        reason = _verify_metadata(row) or _verify_audio(store, row.audio_ref)
        if reason is not None:
            errors.append(ManifestError(contribution_id=row.id, reason=reason))
        else:
            valid.append(row)

    if errors and not allow_partial:
        return ManifestResult(
            written=False,
            output_path=None,
            entries=[],
            errors=errors,
            seed=seed,
        )

    speaker_split: dict[str, str] = {}
    entries: list[dict[str, object]] = []
    for row in valid:
        # Affectation mémorisée par locuteur : une clé ne peut viser deux splits.
        split = speaker_split.setdefault(
            row.speaker_key,
            assign_split(row.speaker_key, seed, splits),
        )
        entries.append(_entry(row, split))

    # Ordre de sortie stable et reproductible.
    entries.sort(key=lambda entry: (entry["split"], entry["speaker_key"], entry["audio_path"]))

    _atomic_write_jsonl(output_path, entries)
    return ManifestResult(
        written=True,
        output_path=output_path,
        entries=entries,
        errors=errors,
        seed=seed,
    )


__all__ = [
    "DEFAULT_SPLITS",
    "DEFAULT_SPLIT_SEED",
    "ManifestError",
    "ManifestResult",
    "assign_split",
    "build_manifest",
]
