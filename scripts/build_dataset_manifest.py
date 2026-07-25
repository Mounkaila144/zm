#!/usr/bin/env python
"""Génération du manifest dataset avec split par locuteur (story 4.5).

Sélectionne les contributions éligibles (``status = validated AND audio_ref
IS NOT NULL``), vérifie chaque audio (présence, lisibilité, WAV mono 16 kHz
PCM16), affecte un split reproductible par ``speaker_key`` et écrit un JSONL
versionné de façon atomique dans ``dataset/manifests/``.

Fail-closed : par défaut, la moindre entrée invalide bloque toute écriture (aucun
manifest partiel). ``--allow-partial`` exclut explicitement les entrées invalides
et publie le reste.

Configuration (via ``Settings``) :
- ``DATABASE_URL``      — base des métadonnées ;
- ``AUDIO_STORAGE_DIR`` — racine du stockage audio consenti (hors Git).

Le manifest ne contient jamais ``anon_id``, ``device_info``, chemin absolu ni
audio brut — seulement une référence audio opaque relative.

Exemples :
    uv run python scripts/build_dataset_manifest.py
    uv run python scripts/build_dataset_manifest.py --output dataset/manifests/manifest.jsonl
    uv run python scripts/build_dataset_manifest.py --seed zarma-dataset-split-v1 --allow-partial
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Permet d'importer le paquet ``app`` même sans installation editable préalable.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_API_ROOT = _REPO_ROOT / "services" / "api"
if _API_ROOT.is_dir() and str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.config import get_settings  # noqa: E402
from app.dataset.manifest import DEFAULT_SPLIT_SEED, build_manifest  # noqa: E402
from app.dataset.session import session_scope  # noqa: E402

_DEFAULT_OUTPUT = _REPO_ROOT / "dataset" / "manifests" / "manifest.jsonl"


async def _run(output: Path, seed: str, allow_partial: bool) -> int:
    audio_root = get_settings().AUDIO_STORAGE_DIR
    async with session_scope() as session:
        result = await build_manifest(
            session=session,
            audio_root=audio_root,
            output_path=output,
            seed=seed,
            allow_partial=allow_partial,
        )
    print(result.summary)
    for error in result.errors:
        print(f"  exclu {error.contribution_id} : {error.reason}", file=sys.stderr)
    if not result.written:
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Générer le manifest dataset (split locuteur).")
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--seed", default=DEFAULT_SPLIT_SEED)
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Exclure les entrées invalides et publier le reste (au lieu de fail-closed).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return asyncio.run(_run(args.output, args.seed, args.allow_partial))


if __name__ == "__main__":
    raise SystemExit(main())
