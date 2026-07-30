"""Télécharge le corpus Feriji (27Group/Feriji, HF) et reconstruit un split
train/val/test déterministe (80/10/10, seed fixe) pour le benchmark.

Le dataset HF est *gated* (accès restreint) : il faut avoir demandé l'accès
sur https://huggingface.co/datasets/27Group/Feriji et disposer d'un token HF
(https://huggingface.co/settings/tokens) placé dans HF_TOKEN (.env).

Le fichier `corpus/fr_dje.jsonl` n'a pas de colonne de split documentée au
moment de l'écriture de ce script — le split ci-dessous est notre propre
reconstruction (mêmes proportions que le papier ACL 2024), pas celui des
auteurs. Si une prochaine version du dataset expose un split officiel,
adapter `_load_corpus` pour le respecter plutôt que de le recalculer.
"""

from __future__ import annotations

import csv
import json
import os
import random
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import hf_hub_download

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEED = 20260727  # fixe : reproductibilité du split entre exécutions
SPLIT_RATIOS = (0.8, 0.1, 0.1)  # train / val / test — reproduit le papier Feriji

# Noms de champs candidats, par ordre de préférence, pour chaque langue.
FRENCH_KEYS = ("french", "francais", "français", "fr", "src", "source")
ZARMA_KEYS = ("zarma", "dje", "tgt", "target")


def _pick_key(row: dict, candidates: tuple[str, ...], label: str) -> str:
    for key in candidates:
        if key in row:
            return key
    raise KeyError(
        f"Impossible de trouver un champ {label} dans une ligne du corpus. "
        f"Clés disponibles : {sorted(row.keys())}. "
        "Inspecter data/corpus_raw.jsonl et ajuster les listes "
        "FRENCH_KEYS/ZARMA_KEYS en tête de ce script."
    )


def _load_corpus(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    fr_key = zarma_key = None
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if fr_key is None:
                fr_key = _pick_key(record, FRENCH_KEYS, "français")
                zarma_key = _pick_key(record, ZARMA_KEYS, "zarma")
            french = (record.get(fr_key) or "").strip()
            zarma = (record.get(zarma_key) or "").strip()
            if french and zarma:
                rows.append({"french": french, "zarma": zarma})
    return rows


def _split(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    shuffled = rows[:]
    random.Random(SEED).shuffle(shuffled)
    n = len(shuffled)
    n_train = int(n * SPLIT_RATIOS[0])
    n_val = int(n * SPLIT_RATIOS[1])
    return {
        "train": shuffled[:n_train],
        "val": shuffled[n_train : n_train + n_val],
        "test": shuffled[n_train + n_val :],
    }


def _load_glossary(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        fr_key = next((c for c in FRENCH_KEYS if c in fieldnames), fieldnames[0])
        zarma_key = next((c for c in ZARMA_KEYS if c in fieldnames), fieldnames[1])
        pairs = []
        for row in reader:
            french = (row.get(fr_key) or "").strip()
            zarma = (row.get(zarma_key) or "").strip()
            if french and zarma:
                pairs.append({"french": french, "zarma": zarma})
        return pairs


def main() -> None:
    load_dotenv()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("HF_TOKEN") or None

    print("Téléchargement du corpus parallèle...")
    corpus_path = Path(
        hf_hub_download(
            repo_id="27Group/Feriji",
            repo_type="dataset",
            filename="corpus/fr_dje.jsonl",
            token=token,
        )
    )
    print("Téléchargement du glossaire...")
    glossary_path = Path(
        hf_hub_download(
            repo_id="27Group/Feriji",
            repo_type="dataset",
            filename="glossary/glossary.csv",
            token=token,
        )
    )

    rows = _load_corpus(corpus_path)
    print(f"{len(rows)} paires de phrases chargées.")
    splits = _split(rows)
    for name, subset in splits.items():
        out_path = DATA_DIR / f"{name}.jsonl"
        with out_path.open("w", encoding="utf-8") as f:
            for row in subset:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"  {name}: {len(subset)} phrases -> {out_path}")

    glossary = _load_glossary(glossary_path)
    glossary_out = DATA_DIR / "glossary.json"
    glossary_out.write_text(
        json.dumps(glossary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Glossaire : {len(glossary)} paires -> {glossary_out}")


if __name__ == "__main__":
    main()
