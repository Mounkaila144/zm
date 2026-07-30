"""Sélectionne les énoncés à enregistrer pour la synthèse vocale des nombres.

Un modèle de synthèse n'apprend pas des mots mais des **transitions sonores**.
Enregistrer 400 nombres au hasard donnerait cinquante fois `zangou` et jamais
`dala` : c'est la couverture qui compte, pas le volume.

Trois unités de couverture, chacune devant apparaître plusieurs fois :

- **(mot, position)** — un mot en fin d'énoncé porte une mélodie descendante,
  au milieu il enchaîne. Ce sont deux réalisations différentes du même mot, et
  un corpus qui n'en contient qu'une produit une voix qui récite.
- **(mot précédent, mot suivant)** — la jonction entre deux mots est l'endroit
  où la concaténation s'entend ; c'est donc ce que le modèle doit surtout
  apprendre.
- **mot** tout court, pour garantir un minimum d'exemples de chacun.

La sélection est gloutonne : à chaque tour on prend l'énoncé qui comble le plus
de déficit restant. Aucune forme zarma n'est écrite à la main — tout vient de
`generate()` et `render_expression()`.

    cd /Users/pc/project/zarma
    research/zarma-assistant/.venv/bin/python \
        research/zarma-assistant/scripts/generate_tts_prompts.py
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import Counter
from pathlib import Path

try:
    from zarma_numbers import Expression, evaluate, generate, render_expression
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "zarma_numbers" / "src"))
    from zarma_numbers import Expression, evaluate, generate, render_expression

DATA = Path(__file__).resolve().parent.parent / "data"

#: Occurrences visées pour chaque unité de couverture. Au-delà de 4-5, le gain
#: devient marginal pour un vocabulaire fermé : le modèle a déjà vu la
#: transition dans assez de contextes.
TARGET = 4

#: Opérandes des expressions — petites valeurs du calcul mental, plus quelques
#: grandes pour que les opérateurs soient aussi entendus après un mot long.
_OPERANDS = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 17, 20, 23, 27, 30, 40,
             50, 60, 70, 80, 90, 100, 115, 150, 200, 250, 350, 400, 500, 600,
             800, 1000, 1500, 2000, 5000, 10000, 100000, 1000000)


def _pool(rng: random.Random) -> list[tuple[str, str]]:
    """(identifiant, texte zarma) — le vivier où puiser."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []

    def add(key: str, text: str) -> None:
        if text not in seen:
            seen.add(text)
            out.append((key, text))

    # Nombres : tout le petit domaine, puis un échantillon large des grandeurs
    # supérieures — c'est là que vivent `dala`, `di` et les échelles.
    valeurs = set(range(0, 201))
    valeurs |= {n for n in range(200, 1000, 7)}
    valeurs |= {n for n in range(1000, 100_000, 137)}
    valeurs |= {n for n in range(100_000, 10_000_000, 9_337)}
    valeurs |= {n * 100_000 + r for n in range(1, 10) for r in (1, 5, 9, 99, 199)}
    valeurs |= {n * 1_000_000 + r for n in range(1, 6) for r in (0, 5, 500, 99_000)}
    for value in sorted(valeurs):
        try:
            add(str(value), generate(value))
        except Exception:  # noqa: BLE001 - hors domaine : ignoré
            continue

    for symbol in ("+", "-", "*", "/"):
        for left in _OPERANDS:
            for right in _OPERANDS:
                if left == right:
                    continue
                expression = Expression(left=left, symbol=symbol, right=right)
                try:
                    evaluate(expression)
                    add(f"{left}{symbol}{right}", render_expression(expression))
                except Exception:  # noqa: BLE001
                    continue

    rng.shuffle(out)
    return out


def _units(text: str) -> set[tuple]:
    """Unités de couverture apportées par un énoncé."""
    mots = text.split()
    units: set[tuple] = set()
    for index, mot in enumerate(mots):
        units.add(("mot", mot))
        if len(mots) == 1:
            position = "seul"
        elif index == 0:
            position = "debut"
        elif index == len(mots) - 1:
            position = "fin"
        else:
            position = "milieu"
        units.add(("position", mot, position))
    for gauche, droite in zip(mots, mots[1:]):
        units.add(("jonction", gauche, droite))
    return units


def _select(pool: list[tuple[str, str]], target: int, limit: int) -> list[tuple[str, str]]:
    besoin: Counter = Counter()
    for _, text in pool:
        for unit in _units(text):
            besoin[unit] = target

    unites = {key: _units(text) for key, text in pool}

    # Amorçage obligatoire : tous les énoncés d'un ou deux mots.
    #
    # Sans cela le glouton n'en retient aucun — une expression de trois mots
    # couvre bien plus d'unités par prise, donc elle gagne toujours. Or la
    # calculatrice énonce ses **résultats**, qui sont souvent un mot unique
    # (`igou` pour 5, `zangou` pour 100), et un mot prononcé seul porte une
    # mélodie que rien d'autre dans le corpus ne contiendrait.
    chosen = [c for c in pool if len(c[1].split()) <= 2]
    chosen.sort(key=lambda c: (len(c[1].split()), c[1]))
    restant = [c for c in pool if c not in chosen]
    for candidat in chosen:
        for unit in unites[candidat[0]]:
            if besoin[unit] > 0:
                besoin[unit] -= 1

    while restant and len(chosen) < limit and any(besoin.values()):
        meilleur, gain_max = None, 0
        for candidat in restant:
            gain = sum(besoin[u] > 0 for u in unites[candidat[0]])
            # À gain égal, l'énoncé le plus court : il coûte moins de souffle à
            # enregistrer et fatigue moins le locuteur sur 400 prises.
            if gain > gain_max or (
                gain == gain_max and gain > 0 and meilleur is not None
                and len(candidat[1]) < len(meilleur[1])
            ):
                meilleur, gain_max = candidat, gain
        if meilleur is None or gain_max == 0:
            break
        chosen.append(meilleur)
        restant.remove(meilleur)
        for unit in unites[meilleur[0]]:
            if besoin[unit] > 0:
                besoin[unit] -= 1
    return chosen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=TARGET)
    parser.add_argument("--limit", type=int, default=400)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output", type=Path, default=DATA / "tts_prompts.csv")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    pool = _pool(rng)
    chosen = _select(pool, args.target, args.limit)

    # Les énoncés courts d'abord : la voix est plus fraîche en début de séance,
    # et ce sont les mots isolés qui serviront de référence au modèle.
    chosen.sort(key=lambda item: (len(item[1].split()), item[1]))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "texte_zarma", "affichage"])
        for key, text in chosen:
            writer.writerow([f"tts_{key}", text, key])

    mots = sorted({m for _, t in chosen for m in t.split()})
    total_mots = sum(len(t.split()) for _, t in chosen)
    # ~0,45 s par mot prononcé, plus ~0,5 s de respiration par énoncé : mesuré
    # sur le corpus existant (nombres à 1 mot 0,80 s, à 3 mots 1,35 s).
    duree = (total_mots * 0.45 + len(chosen) * 0.5) / 60

    manquantes = Counter()
    couvert = Counter()
    for _, text in chosen:
        for unit in _units(text):
            couvert[unit] += 1
    for _, text in pool:
        for unit in _units(text):
            if couvert[unit] < args.target:
                manquantes[unit[0]] += 0  # catégorie connue, compte ci-dessous
    par_type = Counter(u[0] for u in couvert)

    print(f"{len(chosen)} énoncés -> {args.output}")
    print(f"  {len(mots)}/45 mots du vocabulaire présents")
    print(f"  {par_type['position']} couples (mot, position) couverts")
    print(f"  {par_type['jonction']} jonctions entre mots couvertes")
    print(f"  durée de parole estimée : {duree:.0f} minutes")
    print()
    faibles = sorted(m for m in mots if sum(1 for _, t in chosen if m in t.split()) < args.target)
    if faibles:
        print(f"  mots vus moins de {args.target} fois : {', '.join(faibles)}")
    else:
        print(f"  tous les mots apparaissent au moins {args.target} fois")


if __name__ == "__main__":
    main()
