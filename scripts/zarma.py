#!/usr/bin/env python
"""Petit outil de démonstration du moteur ``zarma_numbers``.

Convertit dans les deux sens :
- un **nombre** (0–1 000 000)      → forme zarma canonique ;
- un **texte zarma**               → nombre (ou « non reconnu »).

Usage :
    uv run python scripts/zarma.py 372
    uv run python scripts/zarma.py "zangou hinza nda wayiyye cindi hinka"
    uv run python scripts/zarma.py            # mode interactif

En mode interactif, tape un nombre ou du zarma, puis Entrée. `q` pour quitter.
"""

from __future__ import annotations

import sys

from zarma_numbers import (
    OutOfRangeError,
    UnresolvedFormError,
    generate,
    normalize,
    parse_detailed,
)


def _looks_like_number(text: str) -> bool:
    """Vrai si l'entrée est un entier (chiffres, avec espaces/points/virgules)."""
    cleaned = text.strip().replace(" ", "").replace(".", "").replace(",", "").replace(" ", "")
    return cleaned.isdigit() or (cleaned.startswith("-") and cleaned[1:].isdigit())


def convert(text: str) -> str:
    text = text.strip()
    if not text:
        return ""

    if _looks_like_number(text):
        n = int(text.replace(" ", "").replace(".", "").replace(",", "").replace(" ", ""))
        try:
            return f"{n:,}".replace(",", " ") + "  →  " + generate(n)
        except OutOfRangeError:
            return f"⛔ hors plage : {n} (attendu 0 … 1 000 000)"
        except UnresolvedFormError as exc:
            return f"⛔ forme non résolue ({exc.code})"

    # Sinon : texte zarma → nombre
    result = parse_detailed(text)
    if result.accepted and result.best is not None:
        n = result.best.value
        pretty = f"{n:,}".replace(",", " ")
        return f"« {normalize(text)} »  →  {pretty}"
    return f"❓ non reconnu comme nombre zarma (code : {result.error_code})"


def interactive() -> int:
    print("Moteur zarma_numbers — tape un nombre (0–1 000 000) ou du zarma.")
    print("Ex : 372   |   zambar fo   |   million        (q pour quitter)\n")
    while True:
        try:
            line = input("zarma> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if line.lower() in {"q", "quit", "exit"}:
            return 0
        if line:
            print("  " + convert(line) + "\n")


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        return interactive()
    print(convert(" ".join(argv)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
