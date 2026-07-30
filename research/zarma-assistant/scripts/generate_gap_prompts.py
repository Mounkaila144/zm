"""Construit la liste des phrases à faire enregistrer au tour suivant, à
partir des manques réellement constatés dans le corpus déjà collecté.

Contrairement aux deux générateurs précédents (listes fixes écrites d'avance),
celui-ci lit `data/asr_corpus/manifest.csv` — donc l'état réel de la collecte —
et choisit gloutonnement les énoncés qui rattrapent le plus de mots
sous-représentés. Relancer le script après chaque tour d'enregistrement donne
naturellement la liste suivante, de plus en plus courte.

Ce que le corpus actuel montre : les 4 mots d'opérateur ne sont dits que par 3
voix sur 8, isolément, et **aucune expression complète** n'a jamais été
enregistrée — alors que c'est exactement ce que la calculatrice doit
reconnaître. Viennent ensuite quelques mots rares (`yaamo`, `hakou`, `iddu`,
`wey`, `dala`, `taci`).

Les comptes se font par **voix** et non par dossier : plusieurs dossiers sont
deux séances d'une même personne (cf. `VOICE_ALIASES` dans build_asr_corpus.py),
et un mot déjà dit 40 fois par 2 personnes reste inconnu pour une troisième.

Aucune forme zarma n'est écrite à la main : tout vient de `generate()` et
`render_expression()`, et chaque expression est validée par `evaluate()` — une
opération refusée par le domaine (résultat négatif, division par zéro,
dépassement) ne peut pas se retrouver dans la liste.

    cd /Users/pc/project/zarma
    research/zarma-assistant/.venv/bin/python \
        research/zarma-assistant/scripts/generate_gap_prompts.py
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

try:
    from zarma_numbers import Expression, evaluate, generate, render_expression
except ImportError:  # pragma: no cover - dépannage
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "zarma_numbers" / "src"))
    from zarma_numbers import Expression, evaluate, generate, render_expression

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MANIFEST = DATA_DIR / "asr_corpus" / "manifest.csv"
OUTPUT = DATA_DIR / "asr_recording_prompts_manques.csv"

#: Nombre d'occurrences visé pour chaque mot, tous locuteurs confondus.
TARGET_OCCURRENCES = 60

#: Les 4 mots d'opérateur, dans l'ordre du lexique de `zarma_numbers`.
_OPERATOR_WORDS = {"+": "tonton", "-": "zabou", "*": "ingaybor", "/": "inafaysor"}

#: Opérandes candidates : petites valeurs courantes en calcul mental, plus les
#: valeurs qui portent les mots rares (0 -> yaamo, 600 -> iddu, 800 -> hakou,
#: 115 -> di/wey, 400 -> taci, 100005 -> dala).
_OPERANDS = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 17, 20, 23, 27, 30, 40,
             50, 60, 70, 77, 80, 90, 97, 100, 115, 150, 199, 200, 250, 350, 400,
             600, 800, 999, 1000, 1500, 2000, 4000, 6000, 8000, 10000, 100005,
             1000000)

#: Nombres purs candidats — les porteurs de mots rares d'abord.
_NUMBERS = (0, 400, 600, 800, 4000, 6000, 8000, 115, 215, 415, 615, 815, 100005,
            200005, 800005, 604, 806, 608, 804, 8000005, 6000005, 40, 4, 8, 6,
            1, 2, 3, 5, 7, 9, 10, 20, 30, 100, 1000, 400005, 108, 106)


def _load_counts() -> tuple[Counter[str], int]:
    if not MANIFEST.exists():
        raise SystemExit(
            f"{MANIFEST} introuvable — lancer d'abord build_asr_corpus.py."
        )
    counts: Counter[str] = Counter()
    voices: set[str] = set()
    with MANIFEST.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            # `voix`, pas `locuteur` : deux séances d'une même personne ne font
            # pas deux voix, et c'est le nombre de voix qui dit combien
            # d'occurrences un nouvel énoncé rapportera vraiment.
            voices.add(row["voix"])
            counts.update(row["texte_zarma"].split())
    # Les voix `op*` (dossier operation) ne sont pas encore rattachées : les
    # compter gonflerait le rendement attendu de chaque phrase. On ne retient
    # que les personnes dont on sait qu'elles ont fait un tour complet.
    return counts, len({v for v in voices if not v.startswith("op")})


def _candidates() -> list[tuple[str, str]]:
    """(identifiant, texte zarma) — nombres purs, mots d'opérateur, expressions."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []

    def add(key: str, text: str) -> None:
        if text not in seen:
            seen.add(text)
            out.append((key, text))

    for value in _NUMBERS:
        try:
            add(str(value), generate(value))
        except Exception:  # noqa: BLE001 - hors domaine : simplement ignoré
            continue

    for symbol in ("+", "-", "*", "/"):
        for left in _OPERANDS:
            for right in _OPERANDS:
                # Deux fois la même opérande ferait dire deux fois le même mot
                # dans le même souffle : peu naturel à prononcer, et le contexte
                # acoustique gagné est moindre qu'avec deux nombres différents.
                if left == right:
                    continue
                expression = Expression(left=left, symbol=symbol, right=right)
                try:
                    evaluate(expression)  # refuse négatif / div. par zéro / dépassement
                    text = render_expression(expression)
                except Exception:  # noqa: BLE001
                    continue
                add(f"{left}{symbol}{right}", text)

    return out


def _select(
    counts: Counter[str], voices: int, target: int, limit: int
) -> list[tuple[str, str]]:
    """Sélection gloutonne : à chaque tour, l'énoncé qui comble le plus de
    déficit. Chaque énoncé de la liste sera dit par toutes les personnes, donc
    il rapporte `voices` occurrences par mot — d'où l'importance de compter des
    voix et non des dossiers."""
    deficit = {
        word: max(0, target - count) for word, count in counts.items()
    }
    pool = _candidates()
    # Les 4 mots d'opérateur isolés ouvrent toujours la liste : seules 3 voix
    # sur 8 les ont dits, et le décodeur a besoin de les entendre seuls autant
    # qu'en contexte.
    chosen = [(f"mot{sym}", word) for sym, word in _OPERATOR_WORDS.items()]
    for word in (w for _, w in chosen):
        deficit[word] = max(0, deficit.get(word, 0) - voices)

    # La soustraction est l'opération qui reste le plus facilement dans le
    # domaine (pas de dépassement, pas de reste), donc le choix glouton la
    # retiendrait presque à chaque tour. On plafonne chaque opérateur à une part
    # égale, pour que le modèle ne prenne pas l'habitude d'entendre « zabou ».
    per_operator_cap = max(1, (limit - len(chosen)) // len(_OPERATOR_WORDS))
    used: Counter[str] = Counter()

    while len(chosen) < limit and any(deficit.values()):
        best, best_gain = None, 0
        for candidate in pool:
            symbol = next((s for s in _OPERATOR_WORDS if s in candidate[0]), None)
            if symbol is not None and used[symbol] >= per_operator_cap:
                continue
            gain = sum(min(deficit.get(w, 0), voices) for w in candidate[1].split())
            # À gain égal, préférer l'énoncé le plus court (plus vite enregistré).
            if gain > best_gain or (
                gain == best_gain and best is not None and gain > 0
                and len(candidate[1]) < len(best[1])
            ):
                best, best_gain = candidate, gain
        if best is None or best_gain == 0:
            break
        chosen.append(best)
        pool.remove(best)
        symbol = next((s for s in _OPERATOR_WORDS if s in best[0]), None)
        if symbol is not None:
            used[symbol] += 1
        for word in best[1].split():
            deficit[word] = max(0, deficit.get(word, 0) - voices)

    return chosen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=TARGET_OCCURRENCES,
                        help=f"Occurrences visées par mot (défaut {TARGET_OCCURRENCES})")
    parser.add_argument("--limit", type=int, default=45,
                        help="Nombre maximum de phrases dans la liste (défaut 45)")
    args = parser.parse_args()

    counts, voices = _load_counts()
    chosen = _select(counts, voices, args.target, args.limit)

    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "texte_zarma", "fichier_audio"])
        for key, text in chosen:
            writer.writerow([key, text, ""])

    print(f"{len(chosen)} phrases à enregistrer -> {OUTPUT}")
    print(f"(corpus actuel : {voices} voix, cible {args.target} occurrences/mot)\n")
    for key, text in chosen:
        print(f"  {key:<14} {text}")

    projected = Counter(counts)
    for _, text in chosen:
        for word in text.split():
            projected[word] += voices
    remaining = {w: c for w, c in projected.items() if c < args.target}
    print("\nAprès ce tour (si toutes les voix enregistrent tout) :")
    if remaining:
        print("  mots encore sous la cible : "
              + ", ".join(f"{w} ({c})" for w, c in sorted(remaining.items(), key=lambda kv: kv[1])))
    else:
        print("  tous les mots de la grammaire atteignent la cible.")


if __name__ == "__main__":
    main()
