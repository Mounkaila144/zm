"""Outil de recherche dans le glossaire et le corpus Feriji, pour vérifier
comment un mot ou une expression a déjà été écrite en zarma — utile pendant
la transcription manuelle des enregistrements audio, pour rester cohérent
avec l'orthographe déjà utilisée dans le corpus d'entraînement.

Rappel : le zarma n'a pas d'orthographe officielle. Ce n'est pas un outil de
"vérification orthographique" — c'est une aide pour rester cohérent avec
soi-même et avec le corpus existant, ce qui est ce qui compte réellement
pour entraîner un modèle.

Usage (local, pas besoin de Colab — tourne directement sur le Mac) :
  uv run python scripts/glossary_lookup.py bonjour
  uv run python scripts/glossary_lookup.py "comment allez-vous"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_glossary() -> list[dict[str, str]]:
    path = DATA_DIR / "glossary.json"
    if not path.exists():
        raise SystemExit(f"{path} introuvable — lancer d'abord scripts/download_feriji.py")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_corpus_sample(limit: int = 200_000) -> list[dict[str, str]]:
    rows = []
    for name in ("train.jsonl", "val.jsonl", "test.jsonl"):
        path = DATA_DIR / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
                if len(rows) >= limit:
                    return rows
    return rows


def search(query: str) -> None:
    query_lower = query.strip().lower()
    if not query_lower:
        print("Usage : uv run python scripts/glossary_lookup.py <mot ou expression en français>")
        return

    glossary = _load_glossary()
    glossary_matches = [g for g in glossary if query_lower in g["french"].lower()]

    print(f"\n=== Glossaire ({len(glossary_matches)} résultat(s) pour '{query}') ===")
    for g in glossary_matches[:20]:
        print(f"  {g['french']!r:40s} -> {g['zarma']!r}")
    if len(glossary_matches) > 20:
        print(f"  ... et {len(glossary_matches) - 20} de plus (affinez la recherche)")

    corpus = _load_corpus_sample()
    corpus_matches = [c for c in corpus if query_lower in c["french"].lower()]

    print(f"\n=== Phrases du corpus contenant '{query}' ({len(corpus_matches)} résultat(s)) ===")
    for c in corpus_matches[:10]:
        print(f"\n  FR : {c['french']}")
        print(f"  DJE: {c['zarma']}")
    if len(corpus_matches) > 10:
        print(f"\n  ... et {len(corpus_matches) - 10} de plus (affinez la recherche)")

    if not glossary_matches and not corpus_matches:
        print("\nAucun résultat — ce mot n'apparaît pas dans le corpus Feriji. "
              "Écrivez-le au son, en restant cohérent avec vos propres choix "
              "pour les autres transcriptions.")


if __name__ == "__main__":
    search(" ".join(sys.argv[1:]))
