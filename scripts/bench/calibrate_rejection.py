#!/usr/bin/env python
"""Calibration du seuil de rejet du décodage contraint (story 5.6, task 3).

Le décodage contraint garantit la **validité** d'une sortie, pas sa
**correction** : sans rejet, du bruit produirait un nombre valide (FR21). Le
signal utilisé est la ``confidence`` du décodeur — rapport de vraisemblance par
trame entre le meilleur chemin **contraint** et le meilleur chemin **libre**
(cf. ``services/asr/app/decoding.py``).

Protocole (NFR10 — jamais de calibration sur le split de test)
-------------------------------------------------------------
Entrée : un JSONL d'observations, une ligne par audio décodé :

    {"audio_path": "...", "split": "dev", "is_numeric": true, "confidence": 0.83}

- ``is_numeric`` : vérité terrain — l'audio **est** un énoncé de nombre attendu
  (``true``) ou une entrée non numérique de contrôle : parole quelconque, bruit,
  silence, musique (``false``).
- Le script **refuse** toute ligne du split ``test`` (fail-closed) : la
  calibration se fait sur ``dev``/``calibration`` uniquement. ``--split`` permet
  de restreindre davantage.

Critère de sélection
--------------------
Balayage de tous les seuils candidats (les valeurs de confiance observées) ;
on retient le **plus petit** seuil dont le taux de fausse acceptation
(non-numérique accepté) est ``<= --max-false-acceptance``. À égalité, celui qui
maximise le rappel des vrais nombres. Le rapport liste toute la courbe, pour
que le compromis soit **lisible** et non un chiffre isolé.

Le seuil retenu s'applique via ``DECODE_REJECT_THRESHOLD`` (jamais en dur).

Exécution
---------
    uv run python scripts/bench/calibrate_rejection.py \\
        --observations dataset/benchmark/rejection/dev-observations.jsonl \\
        --max-false-acceptance 0.02 \\
        --out docs/qa/benchmarks/rejection-calibration-v1
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

_BENCH_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BENCH_DIR.parents[1]
if str(_BENCH_DIR) not in sys.path:
    sys.path.insert(0, str(_BENCH_DIR))

from evaluation import atomic_write_text  # noqa: E402

#: Split interdit en calibration (anti-fuite, NFR10).
FORBIDDEN_SPLIT = "test"

#: Version du protocole de calibration (métadonnée de reproductibilité, NFR12).
CALIBRATION_VERSION = "5.6.0"


class CalibrationError(Exception):
    """Erreur contrôlée (fail-closed)."""


@dataclass(frozen=True, slots=True)
class Observation:
    """Une confiance de décodage étiquetée numérique / non numérique."""

    audio_path: str
    split: str
    is_numeric: bool
    confidence: float


@dataclass(frozen=True, slots=True)
class ThresholdPoint:
    """Comportement du rejet à un seuil donné."""

    threshold: float
    #: Nombres correctement laissés passer / total des nombres.
    numeric_kept: int
    numeric_total: int
    #: Non-numériques laissés passer (à minimiser) / total des non-numériques.
    non_numeric_accepted: int
    non_numeric_total: int

    @property
    def recall(self) -> float:
        """Part des vrais nombres qui restent décodés."""
        return round(self.numeric_kept / self.numeric_total, 4) if self.numeric_total else 0.0

    @property
    def false_acceptance_rate(self) -> float:
        """Part des entrées non numériques qui produiraient un nombre (FR21)."""
        if not self.non_numeric_total:
            return 0.0
        return round(self.non_numeric_accepted / self.non_numeric_total, 4)

    @property
    def rejection_rate(self) -> float:
        """Part des entrées non numériques correctement rejetées."""
        return round(1.0 - self.false_acceptance_rate, 4)


def load_observations(path: Path, *, split: str = "all") -> list[Observation]:
    """Charge le JSONL d'observations. Fail-closed sur le split de test."""

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CalibrationError(f"Observations illisibles : {path} ({exc})") from exc

    observations: list[Observation] = []
    for number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            entry = Observation(
                audio_path=str(row["audio_path"]),
                split=str(row.get("split", "dev")),
                is_numeric=bool(row["is_numeric"]),
                confidence=float(row["confidence"]),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise CalibrationError(f"Ligne {number} invalide dans {path.name} ({exc})") from exc

        if entry.split == FORBIDDEN_SPLIT:
            raise CalibrationError(
                f"Ligne {number} : split « {FORBIDDEN_SPLIT} » interdit en calibration "
                "(NFR10 — les seuils ne se calibrent jamais sur le jeu de test)."
            )
        if split != "all" and entry.split != split:
            continue
        observations.append(entry)

    if not observations:
        raise CalibrationError("Aucune observation exploitable après filtrage.")
    return observations


def sweep(observations: list[Observation]) -> list[ThresholdPoint]:
    """Courbe complète rejet / rappel sur tous les seuils candidats."""

    numeric = [o for o in observations if o.is_numeric]
    non_numeric = [o for o in observations if not o.is_numeric]
    # Seuils candidats : 0 (aucun rejet) + chaque confiance observée. Un seuil
    # `t` rejette une observation dont la confiance est strictement inférieure.
    candidates = sorted({0.0} | {o.confidence for o in observations})
    return [
        ThresholdPoint(
            threshold=threshold,
            numeric_kept=sum(1 for o in numeric if o.confidence >= threshold),
            numeric_total=len(numeric),
            non_numeric_accepted=sum(1 for o in non_numeric if o.confidence >= threshold),
            non_numeric_total=len(non_numeric),
        )
        for threshold in candidates
    ]


def select_threshold(
    points: list[ThresholdPoint],
    *,
    max_false_acceptance: float,
) -> ThresholdPoint | None:
    """Plus petit seuil tenant la contrainte de fausse acceptation.

    Retourne ``None`` si **aucun** seuil ne l'atteint — cas où il faut le dire
    plutôt que d'afficher un chiffre flatteur (« ne jamais ajuster un seuil dans
    le seul but d'améliorer le chiffre affiché »).
    """

    eligible = [p for p in points if p.false_acceptance_rate <= max_false_acceptance]
    if not eligible:
        return None
    best = max(eligible, key=lambda p: (p.recall, -p.threshold))
    return best


def build_report(
    points: list[ThresholdPoint],
    selected: ThresholdPoint | None,
    *,
    observations: list[Observation],
    source: Path,
    max_false_acceptance: float,
    split: str,
) -> dict[str, object]:
    """Rapport machine, stable et reproductible."""

    return {
        "calibration_version": CALIBRATION_VERSION,
        "protocol": {
            "signal": "decoding_confidence",
            "definition": "exp(-(nll_contraint - nll_libre) / trames)",
            "split_used": split,
            "forbidden_split": FORBIDDEN_SPLIT,
            "max_false_acceptance": max_false_acceptance,
            "selection_rule": (
                "plus petit seuil dont la fausse acceptation <= max_false_acceptance, "
                "à rappel maximal"
            ),
        },
        "observations": {
            "source": source.name,
            "total": len(observations),
            "numeric": sum(1 for o in observations if o.is_numeric),
            "non_numeric": sum(1 for o in observations if not o.is_numeric),
        },
        "selected": (
            None
            if selected is None
            else {
                "threshold": round(selected.threshold, 6),
                "setting": "DECODE_REJECT_THRESHOLD",
                "recall": selected.recall,
                "false_acceptance_rate": selected.false_acceptance_rate,
                "rejection_rate": selected.rejection_rate,
            }
        ),
        "curve": [
            {
                "threshold": round(p.threshold, 6),
                "recall": p.recall,
                "false_acceptance_rate": p.false_acceptance_rate,
                "rejection_rate": p.rejection_rate,
                "numeric_kept": p.numeric_kept,
                "numeric_total": p.numeric_total,
                "non_numeric_accepted": p.non_numeric_accepted,
                "non_numeric_total": p.non_numeric_total,
            }
            for p in points
        ],
    }


def report_to_markdown(report: dict) -> str:
    """Rend le rapport lisible pour la revue QA."""

    selected = report["selected"]
    obs = report["observations"]
    lines = [
        "# Calibration du seuil de rejet — décodage contraint (story 5.6)",
        "",
        f"- **Protocole** : {report['calibration_version']} · signal "
        f"`{report['protocol']['signal']}` = `{report['protocol']['definition']}`",
        f"- **Split utilisé** : `{report['protocol']['split_used']}` "
        f"(split `{report['protocol']['forbidden_split']}` interdit — NFR10)",
        f"- **Observations** : {obs['total']} ({obs['numeric']} numériques, "
        f"{obs['non_numeric']} non numériques) — source `{obs['source']}`",
        f"- **Contrainte** : fausse acceptation ≤ {report['protocol']['max_false_acceptance']}",
        "",
    ]
    if selected is None:
        lines += [
            "## ⚠️ Aucun seuil retenu",
            "",
            "Aucun seuil du balayage ne tient la contrainte de fausse acceptation.",
            "Le seuil reste à `0.0` (aucun rejet) : mieux vaut l'absence de rejet",
            "qu'un seuil non justifié. Voir la courbe ci-dessous pour arbitrer.",
            "",
        ]
    else:
        lines += [
            f"## Seuil retenu : **{selected['threshold']}** " f"(`{selected['setting']}`)",
            "",
            f"- rappel des vrais nombres : **{selected['recall']:.4f}**",
            f"- fausse acceptation (non numérique → nombre) : "
            f"**{selected['false_acceptance_rate']:.4f}**",
            f"- rejet correct des non-numériques : **{selected['rejection_rate']:.4f}**",
            "",
        ]
    lines += [
        "## Courbe complète",
        "",
        "| seuil | rappel | fausse acceptation | rejet correct |",
        "|---|---|---|---|",
    ]
    for point in report["curve"]:
        lines.append(
            f"| {point['threshold']} | {point['recall']:.4f} | "
            f"{point['false_acceptance_rate']:.4f} | {point['rejection_rate']:.4f} |"
        )
    return "\n".join(lines) + "\n"


def _run(args: argparse.Namespace) -> int:
    try:
        observations = load_observations(args.observations, split=args.split)
    except CalibrationError as exc:
        print(f"Calibration refusée : {exc}", file=sys.stderr)
        return 2

    points = sweep(observations)
    selected = select_threshold(points, max_false_acceptance=args.max_false_acceptance)
    report = build_report(
        points,
        selected,
        observations=observations,
        source=args.observations,
        max_false_acceptance=args.max_false_acceptance,
        split=args.split,
    )

    json_path = args.out.with_suffix(".json")
    md_path = args.out.with_suffix(".md")
    atomic_write_text(json_path, json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    atomic_write_text(md_path, report_to_markdown(report))

    if selected is None:
        print(
            "Aucun seuil ne tient la contrainte de fausse acceptation "
            f"(≤ {args.max_false_acceptance}) → DECODE_REJECT_THRESHOLD reste 0.0. "
            f"Courbe complète : {md_path.name}",
            file=sys.stderr,
        )
        return 1

    print(
        f"DECODE_REJECT_THRESHOLD={selected.threshold:.6f} "
        f"(rappel {selected.recall:.4f}, fausse acceptation "
        f"{selected.false_acceptance_rate:.4f}) → {json_path.name}, {md_path.name}"
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Calibration du seuil de rejet (story 5.6).")
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--split", default="all", help="dev | calibration | all (défaut : all)")
    parser.add_argument("--max-false-acceptance", type=float, default=0.02)
    parser.add_argument(
        "--out",
        type=Path,
        default=_REPO_ROOT / "docs" / "qa" / "benchmarks" / "rejection-calibration",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    return _run(_build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
