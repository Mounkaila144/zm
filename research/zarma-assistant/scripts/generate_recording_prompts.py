"""Génère une liste de nombres à enregistrer en zarma, pour constituer un
premier jeu de données d'entraînement pour un modèle de reconnaissance
vocale local et léger (Chemin B — voir discussion dans le projet).

Réutilise `zarma_numbers.generator.generate()` (déjà validé par les tests du
package) plutôt que d'inventer des exemples à la main — la forme canonique
de chaque nombre est donc garantie correcte, y compris les cas particuliers
de la grammaire (connecteur da/di, marqueur dala, élision).

IMPORTANT : ce script utilise le paquet `zarma_numbers` du workspace racine
du monorepo — il faut donc le lancer depuis la RACINE du projet (pas depuis
research/zarma-assistant), avec l'environnement Python racine :

    cd /Users/pc/project/zarma
    uv run python research/zarma-assistant/scripts/generate_recording_prompts.py

Produit un CSV avec une colonne `nombre`, une colonne `texte_zarma` (à lire
à voix haute et enregistrer) et une colonne `fichier_audio` vide (à remplir
avec le nom du fichier une fois l'enregistrement fait).
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

try:
    from zarma_numbers.generator import generate
except ImportError:
    print(
        "Erreur : zarma_numbers introuvable. Ce script doit être lancé depuis "
        "la racine du monorepo avec l'environnement racine :\n"
        "  cd /Users/pc/project/zarma\n"
        "  uv run python research/zarma-assistant/scripts/generate_recording_prompts.py",
        file=sys.stderr,
    )
    raise

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "asr_recording_prompts.csv"


def _stratified_numbers() -> list[int]:
    """Échantillon couvrant toute la grammaire : unités, dizaines, centaines,
    milliers, millions, et les cas particuliers documentés dans generator.py
    (marqueur `dala`, connecteur `da`/`di` élidé)."""
    numbers: set[int] = set()

    # Unités isolées (0-9) — forme de base, la plus fréquente à l'usage.
    numbers.update(range(0, 10))

    # Dizaines : chaque dizaine pleine + quelques combinaisons avec reste,
    # en couvrant les têtes qui déclenchent le connecteur élidé (2,3,4,5,10)
    # et celles qui ne le déclenchent pas.
    for tens in range(10, 100, 10):
        numbers.add(tens)
        numbers.add(tens + 3)
        numbers.add(tens + 7)

    # Centaines : avec/sans reste, hundreds_digit=1 (omis) et >1.
    numbers.update({100, 101, 115, 150, 199, 200, 233, 350, 999})

    # Milliers : multiplicateur simple et composé, avec/sans reste, y compris
    # le cas où le marqueur `dala` doit apparaître (multiplicateur multiple
    # de 100, ex. 100 000 + reste = multiplicateur 100).
    numbers.update({1_000, 1_001, 1_500, 2_000, 5_432, 12_345, 100_005, 999_999})

    # Millions : y compris le cas "million" seul (bare multiplier omis).
    numbers.update({1_000_000, 1_000_001, 2_000_000, 1_500_000, 12_000_500})

    return sorted(numbers)


def main() -> None:
    numbers = _stratified_numbers()
    rows = []
    skipped = []
    for n in numbers:
        try:
            rows.append({"nombre": n, "texte_zarma": generate(n), "fichier_audio": ""})
        except Exception as exc:  # forme non résolue dans le lexique — on l'ignore proprement
            skipped.append((n, str(exc)))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["nombre", "texte_zarma", "fichier_audio"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)} phrases générées -> {OUTPUT_PATH}")
    if skipped:
        print(f"{len(skipped)} nombre(s) ignoré(s) (forme non résolue dans le lexique) :")
        for n, reason in skipped:
            print(f"  {n}: {reason}")


if __name__ == "__main__":
    main()
