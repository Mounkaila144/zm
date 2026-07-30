"""Génère la liste des mots d'opération (+ - x ÷) et d'expressions complètes
à enregistrer en zarma — complément à generate_recording_prompts.py, qui ne
couvrait que les nombres purs (oubli signalé après le premier tour
d'enregistrement).

Réutilise le lexique d'opérateurs et `render_expression()` du paquet
`zarma_numbers` (déjà validés par ses tests) — aucune forme n'est inventée
ici.

IMPORTANT : comme generate_recording_prompts.py, à lancer depuis la RACINE
du monorepo :

    cd /Users/pc/project/zarma
    uv run python research/zarma-assistant/scripts/generate_operator_prompts.py

Produit un CSV séparé (asr_recording_prompts_operations.csv) — à enregistrer
en plus des 59 phrases déjà faites, pas à la place.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

try:
    from zarma_numbers.expressions import Expression, render_expression, supported_operators
except ImportError:
    print(
        "Erreur : zarma_numbers introuvable. Lancer depuis la racine du monorepo :\n"
        "  cd /Users/pc/project/zarma\n"
        "  uv run python research/zarma-assistant/scripts/generate_operator_prompts.py",
        file=sys.stderr,
    )
    raise

OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "asr_recording_prompts_operations.csv"
)

#: Nom de fichier sûr par opérateur (pas de +, /, × dans un nom de fichier).
_OPERATOR_SLUGS = {"+": "plus", "-": "moins", "*": "fois", "/": "div"}

#: (gauche, droite) par opérateur — couvre des grandeurs variées et, pour la
#: division, un cas exact et un cas avec reste (« ga cindi »).
_EXPRESSION_SAMPLES: dict[str, list[tuple[int, int]]] = {
    "+": [(2, 3), (23, 5), (100, 30), (1500, 250)],
    "-": [(5, 2), (50, 23), (200, 100), (1000, 1)],
    "*": [(3, 4), (12, 5), (100, 3)],
    "/": [(10, 2), (100, 4), (23, 5)],  # 23/5 = reste -> teste le marqueur "ga cindi"
}


def main() -> None:
    rows: list[dict[str, str]] = []

    # 1. Mots d'opérateur isolés — vocabulaire de base, comme les mots-nombres.
    for symbol, name in supported_operators().items():
        # On lit le mot d'opérateur seul en le prononçant tel qu'utilisé dans
        # une expression : "tonton" (+), "zabou" (-), "ingaybor" (x), "inafaysor" (÷).
        expr = Expression(left=0, symbol=symbol, right=0)
        word = render_expression(expr).split()[1]  # "0 <mot> 0" -> le mot du milieu
        slug = _OPERATOR_SLUGS[symbol]
        rows.append({"id": f"mot_{slug}", "texte_zarma": word, "fichier_audio": ""})

    # 2. Expressions complètes — pour que le modèle apprenne l'opérateur *dans*
    # une phrase parlée naturellement, pas seulement isolé.
    for symbol, pairs in _EXPRESSION_SAMPLES.items():
        slug = _OPERATOR_SLUGS[symbol]
        for left, right in pairs:
            expr = Expression(left=left, symbol=symbol, right=right)
            text = render_expression(expr)
            rows.append(
                {"id": f"{left}_{slug}_{right}", "texte_zarma": text, "fichier_audio": ""}
            )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "texte_zarma", "fichier_audio"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)} phrases générées -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
