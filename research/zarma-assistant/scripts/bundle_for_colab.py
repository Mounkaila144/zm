"""Fabrique l'archive unique à téléverser sur Colab.

Rassemble tout ce dont l'entraînement a besoin — corpus, code d'entraînement,
grammaire zarma et décodeur contraint — dans un seul `zarma_asr.zip`. Un seul
fichier à déposer sur Drive, au lieu de tenir à jour un zip de données d'un
côté et un script de l'autre : la principale source d'erreurs jusqu'ici a été
d'oublier de recopier le script modifié dans la session.

    cd /Users/pc/project/zarma
    research/zarma-assistant/.venv/bin/python \
        research/zarma-assistant/scripts/bundle_for_colab.py

Contenu de l'archive (tout est à la racine `zarma_asr/`, donc importable sans
manipuler PYTHONPATH une fois dans le dossier) :

    asr_corpus/            clips + manifest + fonds sonores
    zarma_numbers/         grammaire, générateur, parseur (+ lexicon.yaml)
    decoding.py            décodeur CTC contraint (services/asr/app)
    train_asr_v1_colab.py  entraînement
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "research" / "zarma-assistant"

SOURCES = {
    "asr_corpus": RESEARCH / "data" / "asr_corpus",
    "zarma_numbers": ROOT / "packages" / "zarma_numbers" / "src" / "zarma_numbers",
    "decoding.py": ROOT / "services" / "asr" / "app" / "decoding.py",
    "train_asr_v1_colab.py": Path(__file__).with_name("train_asr_v1_colab.py"),
}

#: Exclus de l'archive : bytecode compilé pour une autre version de Python (le
#: Mac est en 3.14, Colab en 3.12 — des .pyc étrangers ne servent à rien et
#: peuvent semer la confusion) et les artefacts macOS.
EXCLUDED = {"__pycache__", ".DS_Store", ".pytest_cache"}


def _keep(path: Path) -> bool:
    return not any(part in EXCLUDED for part in path.parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=RESEARCH / "data" / "zarma_asr.zip"
    )
    args = parser.parse_args()

    missing = [name for name, path in SOURCES.items() if not path.exists()]
    if missing:
        raise SystemExit(
            "Introuvable : "
            + ", ".join(f"{n} ({SOURCES[n]})" for n in missing)
            + "\nLancer build_asr_corpus.py d'abord si c'est le corpus qui manque."
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, source in SOURCES.items():
            if source.is_file():
                archive.write(source, f"zarma_asr/{name}")
                total += 1
                continue
            for path in sorted(source.rglob("*")):
                if path.is_file() and _keep(path.relative_to(source)):
                    archive.write(path, f"zarma_asr/{name}/{path.relative_to(source)}")
                    total += 1

    size_mb = args.output.stat().st_size / 1e6
    print(f"{args.output}  ({size_mb:.0f} Mo, {total} fichiers)")
    print(
        "\nÀ déposer sur Drive, puis dans Colab :\n"
        "    from google.colab import drive; drive.mount('/content/drive')\n"
        "    %cd /content\n"
        "    !cp /content/drive/MyDrive/zarma_asr_v1/zarma_asr.zip .\n"
        "    !unzip -oq zarma_asr.zip\n"
        "    %cd zarma_asr\n"
        "    !pip -q install -U transformers soundfile pyyaml\n"
        "    !python train_asr_v1_colab.py --corpus asr_corpus \\\n"
        "        --output /content/drive/MyDrive/zarma_asr_v1/resultats"
    )


if __name__ == "__main__":
    main()
