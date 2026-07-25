#!/usr/bin/env python
"""Restitution vocale zarma par concaténation — ligne de commande (story 6.1, task 6).

Le vocabulaire des nombres est **fermé (33 mots)** : dire n'importe quel nombre
de 0 à 1 000 000, ou n'importe quel résultat d'opération, ne demande donc pas de
synthèse vocale entraînée — seulement une **banque de mots enregistrés**
assemblés dans l'ordre. C'est la modalité retenue en décision D3, la seule
utilisable par un utilisateur qui ne lit pas.

Toute la logique vit dans ``voice_bank.py`` (testée sans audio réel) ; ce
fichier n'est que son interface.

**Fail-closed** (FR21) : s'il manque un seul segment, **rien** n'est produit.
Prononcer un résultat à moitié serait indétectable pour la cible — donc pire
que le silence.

Banque vocale
-------------
- les nombres déjà enregistrés (``v<N>-<nombre>.wav``) dont la forme tient en un
  mot alimentent la banque automatiquement ;
- les mots restants sont déposés en ``<mot>.wav`` dans ``--bank-dir`` ;
- les **consignes** entières (« c'est bien … ? », « je ne peux pas répondre »)
  sont déposées en ``confirm.wav`` / ``cannot_answer.wav`` dans ``--prompt-dir``.
  Elles ne sont pas composables : un locuteur natif les enregistre.

Usage
-----
    # Que manque-t-il pour couvrir 0–1 000 000 et les consignes ?
    uv run python scripts/speech/say_number.py --voice v1 --list-missing

    # Prononcer un nombre, un résultat, une confirmation
    uv run python scripts/speech/say_number.py --voice v1 --number 20 --out /tmp/20.wav
    uv run python scripts/speech/say_number.py --voice v1 --expression "103 / 5" --out /tmp/r.wav
    uv run python scripts/speech/say_number.py --voice v1 --number 42 --confirm --out /tmp/c.wav
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Rend le cœur importable quel que soit le répertoire d'appel.
_SPEECH_DIR = Path(__file__).resolve().parent
if str(_SPEECH_DIR) not in sys.path:
    sys.path.insert(0, str(_SPEECH_DIR))

from voice_bank import (  # noqa: E402
    VoiceBankError,
    build_bank,
    confirmation_utterance,
    duration_seconds,
    expression_utterance,
    missing_prompts,
    missing_vocabulary,
    number_coverage,
    number_utterance,
    refusal_utterance,
    result_utterance,
    synthesize,
    write_wav,
)
from zarma_numbers.exceptions import DomainError  # noqa: E402
from zarma_numbers.expressions import (  # noqa: E402
    Expression,
    evaluate,
    render_expression,
    render_result,
)
from zarma_numbers.generator import generate  # noqa: E402

#: Séparateur accepté dans ``--expression`` (ex. « 103 / 5 »).
_SYMBOLS = ("+", "-", "*", "/")


def parse_cli_expression(text: str) -> Expression:
    """Lit ``"<gauche> <symbole> <droite>"`` — saisie de test, pas une entrée utilisateur."""
    for symbol in _SYMBOLS:
        left, found, right = text.partition(symbol)
        if found:
            return Expression(int(left.strip()), symbol, int(right.strip()))
    raise ValueError(f"Expression illisible : {text!r} (attendu « 103 / 5 »).")


def _cmd_list_missing(bank) -> int:
    words = missing_vocabulary(bank)
    prompts = missing_prompts(bank)
    print(f"\n{len(words)} mot(s) à enregistrer (déposer en <mot>.wav dans --bank-dir) :")
    for word in words:
        print(f"  - {word}")
    print(f"\n{len(prompts)} consigne(s) à enregistrer (<nom>.wav dans --prompt-dir) :")
    for name in prompts:
        print(f"  - {name}")
    return 0


def _utterance_for(args):
    """Construit l'énoncé demandé, et le texte à afficher pour la traçabilité."""
    if args.expression is not None:
        expression = parse_cli_expression(args.expression)
        if args.echo:
            return expression_utterance(expression), render_expression(expression)
        result = evaluate(expression)  # DomainError remonte : traité par l'appelant
        return result_utterance(result), render_result(result)
    return number_utterance(args.number), generate(args.number)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prononce un nombre ou un résultat zarma.")
    parser.add_argument("--voice", default="v1", help="Locuteur (v1, v2, v3…).")
    parser.add_argument("--number", type=int, default=None)
    parser.add_argument("--expression", default=None, help='Opération, ex. "103 / 5".')
    parser.add_argument(
        "--echo",
        action="store_true",
        help="Avec --expression : relire l'opération au lieu d'en dire le résultat.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Préfixer de la consigne de confirmation (« c'est bien … ? »).",
    )
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--bank-dir", type=Path, default=None, help="Mots enregistrés à l'unité.")
    parser.add_argument("--prompt-dir", type=Path, default=None, help="Consignes enregistrées.")
    parser.add_argument("--list-missing", action="store_true")
    parser.add_argument("--coverage", action="store_true", help="Combien de nombres 0–1000 ?")
    args = parser.parse_args(argv)

    bank = build_bank(args.voice, word_dir=args.bank_dir, prompt_dir=args.prompt_dir)
    print(
        f"Banque « {args.voice} » : {len(bank.words)} mot(s), "
        f"{len(bank.prompts)} consigne(s) disponible(s)."
    )

    if args.list_missing:
        return _cmd_list_missing(bank)

    if args.coverage:
        ok, total = number_coverage(bank)
        print(f"Couverture : {ok}/{total} nombres de 0 à 1000 prononçables.")
        return 0

    if args.number is None and args.expression is None:
        parser.error("--number ou --expression est requis (ou --list-missing / --coverage)")

    try:
        utterance, form = _utterance_for(args)
    except DomainError as exc:
        # Hors domaine : on ANNONCE le refus, on ne se tait pas — se taire serait
        # indistinguable d'une panne pour un utilisateur qui ne lit pas (AC4).
        print(f"hors domaine ({exc.code}) → consigne de refus")
        utterance, form = refusal_utterance(), f"[refus : {exc.code}]"

    if args.confirm:
        utterance = confirmation_utterance(utterance)

    try:
        pcm = synthesize(utterance, bank)
    except VoiceBankError as exc:
        print(f"⛔ {exc}", flush=True)
        return 1

    print(f"« {form} »  ({duration_seconds(pcm):.2f}s)")
    if args.out:
        write_wav(args.out, pcm)
        print(f"écrit : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
