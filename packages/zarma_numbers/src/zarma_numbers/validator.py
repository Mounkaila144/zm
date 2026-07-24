"""Invariant exhaustif ``parse(normalize(generate(n))) == n`` (story 1.6).

C'est le nœud de dérisquage du projet : il **prouve** que le moteur linguistique
déterministe convertit nombre ↔ zarma sans perte, indépendamment de l'ASR.

Portée de la preuve (depuis story 1.7) :

- Plage **entière** ``0``–``1 000 000`` : l'invariant DOIT tenir ; toute
  violation est une **erreur** (fait échouer la CI). Le marqueur ``dala`` lève
  l'ambiguïté ``≥ 100 000`` et la forme ``million`` résout ``1 000 000``.
- Une éventuelle forme encore ``unresolved`` (``generate`` lève
  ``UnresolvedFormError``) reste **tracée**, pas comptée comme échec.

Exécuter : ``uv run python -m zarma_numbers.validator`` (ou ``make invariant``).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from .exceptions import UnresolvedFormError
from .generator import MAX_VALUE, generate
from .normalizer import normalize
from .parser import parse

#: Borne supérieure de la plage où l'invariant est **garanti** (toute la plage
#: depuis la story 1.7 : dala + million ferment les ambiguïtés ≥ 100 000).
RESOLVED_MAX = MAX_VALUE


@dataclass
class InvariantReport:
    """Rapport de l'invariant sur un intervalle."""

    start: int
    end: int
    ok: int = 0
    unresolved: list[int] = field(default_factory=list)
    ambiguous: list[int] = field(default_factory=list)
    violations: list[tuple[int, str, int | None]] = field(default_factory=list)

    @property
    def has_violations(self) -> bool:
        return bool(self.violations)

    def summary(self) -> str:
        lines = [
            f"Invariant parse(normalize(generate(n))) == n sur [{self.start}, {self.end}]",
            f"  OK (roundtrip vérifié)      : {self.ok}",
            f"  unresolved (forme null)     : {len(self.unresolved)}",
            f"  ambiguous (>{RESOLVED_MAX}, non résolu) : {len(self.ambiguous)}",
            f"  VIOLATIONS (forme résolue)  : {len(self.violations)}",
        ]
        for n, text, got in self.violations[:10]:
            lines.append(f"    ✗ n={n} generate={text!r} parse={got!r}")
        return "\n".join(lines)


def validate_invariant(
    start: int = 0,
    end: int = MAX_VALUE,
    resolved_max: int = RESOLVED_MAX,
) -> InvariantReport:
    """Vérifie l'invariant sur ``[start, end]`` et retourne un rapport.

    - roundtrip correct → ``ok`` ;
    - ``generate`` lève ``UnresolvedFormError`` → ``unresolved`` ;
    - roundtrip incorrect au-delà de ``resolved_max`` → ``ambiguous`` (tracé) ;
    - roundtrip incorrect à/en-deçà de ``resolved_max`` → ``violations`` (échec).
    """
    report = InvariantReport(start=start, end=end)
    for n in range(start, end + 1):
        try:
            text = generate(n)
        except UnresolvedFormError:
            report.unresolved.append(n)
            continue
        got = parse(normalize(text))
        if got == n:
            report.ok += 1
        elif n > resolved_max:
            report.ambiguous.append(n)
        else:
            report.violations.append((n, text, got))
    return report


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    start = int(argv[0]) if len(argv) > 0 else 0
    end = int(argv[1]) if len(argv) > 1 else MAX_VALUE
    report = validate_invariant(start, end)
    print(report.summary())
    return 1 if report.has_violations else 0


__all__ = ["validate_invariant", "InvariantReport", "RESOLVED_MAX"]


if __name__ == "__main__":
    sys.exit(main())
