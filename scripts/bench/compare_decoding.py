#!/usr/bin/env python
"""Comparaison **glouton vs contraint** via le harnais 5.2 (story 5.6, task 5).

Ce script ne calcule **aucune métrique** : il appelle le harnais d'évaluation de
la story 5.2 (``evaluation.evaluate`` / ``build_report``) sur deux jeux
d'hypothèses — le décodage glouton (pipeline officiel) et le décodage contraint
(story 5.6) — puis met les deux rapports côte à côte, ventilés par **condition**,
**tranche de nombres** (tag ``short``/``long``/``confusion``) et **split**.

Les chiffres de décision se lisent sur le split ``test`` (locuteurs jamais vus,
NFR10) ; ``--split all`` reste possible pour l'analyse.

La **référence du prototype** (Annexe A §4 de la story : 73 % global, 79 % sur
locuteur non vu, corpus 3 locuteurs / 99 fichiers) est rappelée dans le rapport
pour situer le gain, et l'écart aux objectifs **NFR2** (≥ 95 % calme,
≥ 90 % bruit modéré) est calculé **par condition**, sans jamais être masqué.

Exécution (les deux JSONL viennent de ``run_benchmark.py --dump-hypotheses``) :

    uv run python scripts/bench/compare_decoding.py \\
        --manifest dataset/manifests/benchmark.jsonl \\
        --greedy dataset/benchmark/hypotheses/ctc-greedy.jsonl \\
        --constrained dataset/benchmark/hypotheses/ctc-constrained.jsonl \\
        --split test --out docs/qa/benchmarks/decoding-greedy-vs-constrained-v1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BENCH_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BENCH_DIR.parents[1]
_API_ROOT = _REPO_ROOT / "services" / "api"
for _path in (_BENCH_DIR, _API_ROOT):
    if _path.is_dir() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from app.config import get_settings  # noqa: E402
from benchmark_corpus import read_manifest  # noqa: E402
from evaluation import (  # noqa: E402
    EvaluationError,
    atomic_write_text,
    build_report,
    evaluate,
    load_hypotheses,
    replay_source,
)

#: Version du protocole de comparaison (reproductibilité, NFR12).
COMPARISON_VERSION = "5.6.0"

#: Référence mesurée du prototype (Annexe A §4) — le gain se juge contre elle.
PROTOTYPE_REFERENCE = {
    "source": "docs/stories/5.6.story.md — Annexe A §4",
    "corpus": "3 locuteurs, 99 fichiers, 52 nombres distincts (0→10 000), condition calme",
    "greedy_accuracy": 0.02,
    "constrained_accuracy": 0.73,
    "constrained_accuracy_unseen_speaker": 0.79,
    "note": "espace de recherche 1010 candidats énumérés ; le décodeur 5.6 couvre 0–1 000 000",
}

#: Objectifs de qualité NFR2, par condition.
NFR2_TARGETS = {"calme": 0.95, "bruit": 0.90}


def _accuracy_gap(report: dict) -> list[dict[str, object]]:
    """Écart aux objectifs NFR2, par condition — documenté, jamais masqué."""

    by_condition = report["metrics"]["by_condition"]  # type: ignore[index]
    gaps: list[dict[str, object]] = []
    for condition, target in sorted(NFR2_TARGETS.items()):
        group = by_condition.get(condition)
        if group is None:
            gaps.append({"condition": condition, "target": target, "measured": None, "gap": None})
            continue
        measured = float(group["accuracy"])
        gaps.append(
            {
                "condition": condition,
                "target": target,
                "measured": measured,
                "gap": round(measured - target, 4),
                "meets_target": measured >= target,
                "correct": group["correct"],
                "total": group["total"],
            }
        )
    return gaps


def _delta(constrained: dict, greedy: dict, path: tuple[str, ...]) -> dict[str, object]:
    """Compare un même groupe entre les deux rapports."""

    def dig(report: dict) -> dict | None:
        node: object = report
        for key in path:
            if not isinstance(node, dict) or key not in node:
                return None
            node = node[key]
        return node if isinstance(node, dict) else None

    left, right = dig(constrained), dig(greedy)
    if left is None or right is None:
        return {"constrained": None, "greedy": None, "delta": None}
    return {
        "constrained": left["accuracy"],
        "greedy": right["accuracy"],
        "delta": round(float(left["accuracy"]) - float(right["accuracy"]), 4),
        "constrained_correct": f"{left['correct']}/{left['total']}",
        "greedy_correct": f"{right['correct']}/{right['total']}",
    }


def build_comparison(greedy: dict, constrained: dict, *, split: str) -> dict[str, object]:
    """Assemble le rapport de comparaison (aucune métrique recalculée)."""

    groups = ("by_condition", "by_tag", "by_split")
    breakdown: dict[str, dict[str, object]] = {}
    for group in groups:
        names = sorted(
            set(constrained["metrics"][group]) | set(greedy["metrics"][group])  # type: ignore[index]
        )
        breakdown[group] = {
            name: _delta(constrained, greedy, ("metrics", group, name)) for name in names
        }

    greedy_accuracy = float(greedy["metrics"]["exact_number_accuracy"])  # type: ignore[index]
    constrained_accuracy = float(constrained["metrics"]["exact_number_accuracy"])  # type: ignore[index]

    return {
        "comparison_version": COMPARISON_VERSION,
        "split_evaluated": split,
        "harness_version": constrained["harness_version"],
        "grammar_version": constrained["versions"]["grammar_version"],  # type: ignore[index]
        "manifest": constrained["manifest"],
        "overall": {
            "greedy": greedy_accuracy,
            "constrained": constrained_accuracy,
            "delta": round(constrained_accuracy - greedy_accuracy, 4),
            "greedy_correct": f"{greedy['metrics']['correct']}/{greedy['metrics']['total']}",
            "constrained_correct": (
                f"{constrained['metrics']['correct']}/{constrained['metrics']['total']}"
            ),
        },
        "breakdown": breakdown,
        "decision_rates": {
            "greedy": greedy["metrics"]["decision_rates"],  # type: ignore[index]
            "constrained": constrained["metrics"]["decision_rates"],  # type: ignore[index]
        },
        "asr_latency_ms": {
            "greedy": greedy["metrics"]["asr_latency_ms"],  # type: ignore[index]
            "constrained": constrained["metrics"]["asr_latency_ms"],  # type: ignore[index]
        },
        "prototype_reference": PROTOTYPE_REFERENCE,
        "nfr2": {
            "targets": NFR2_TARGETS,
            "constrained_gap": _accuracy_gap(constrained),
        },
        "reports": {
            "greedy": {
                "model_versions": greedy["asr"]["model_versions"],  # type: ignore[index]
                "mode": greedy["asr"]["mode"],  # type: ignore[index]
            },
            "constrained": {
                "model_versions": constrained["asr"]["model_versions"],  # type: ignore[index]
                "mode": constrained["asr"]["mode"],  # type: ignore[index]
            },
        },
    }


def comparison_to_markdown(comparison: dict) -> str:
    """Rapport lisible pour la revue QA (le gain doit sauter aux yeux)."""

    overall = comparison["overall"]
    lines = [
        f"# Décodage glouton vs contraint — split `{comparison['split_evaluated']}`",
        "",
        f"- **Protocole** : comparaison {comparison['comparison_version']} "
        f"· harnais 5.2 `{comparison['harness_version']}` (aucune métrique réimplémentée)",
        f"- **grammar_version** : {comparison['grammar_version']}",
        f"- **Manifest** : `{comparison['manifest']['name']}` "
        f"(sha256 `{comparison['manifest']['sha256'][:12]}…`, "
        f"{comparison['manifest']['entries']} audios)",
        "",
        "## Exact Number Accuracy",
        "",
        "| décodage | accuracy | correct/total |",
        "|---|---|---|",
        f"| glouton | {overall['greedy']:.4f} | {overall['greedy_correct']} |",
        f"| **contraint** | **{overall['constrained']:.4f}** | {overall['constrained_correct']} |",
        f"| **gain** | **{overall['delta']:+.4f}** | — |",
        "",
    ]

    titles = {
        "by_condition": "Par condition",
        "by_tag": "Par tranche de nombres (tag)",
        "by_split": "Par split",
    }
    for group, title in titles.items():
        lines += [
            f"### {title}",
            "",
            "| groupe | glouton | contraint | gain |",
            "|---|---|---|---|",
        ]
        for name, values in comparison["breakdown"][group].items():
            if values["delta"] is None:
                lines.append(f"| {name} | — | — | — |")
                continue
            lines.append(
                f"| {name} | {values['greedy']:.4f} | {values['constrained']:.4f} | "
                f"{values['delta']:+.4f} |"
            )
        lines.append("")

    reference = comparison["prototype_reference"]
    lines += [
        "## Comparaison à la référence du prototype (Annexe A §4)",
        "",
        f"- corpus de référence : {reference['corpus']}",
        f"- glouton mesuré alors : {reference['greedy_accuracy']:.2f} · "
        f"contraint : {reference['constrained_accuracy']:.2f} "
        f"(locuteur non vu : {reference['constrained_accuracy_unseen_speaker']:.2f})",
        f"- ici (contraint, split `{comparison['split_evaluated']}`) : "
        f"**{overall['constrained']:.4f}**",
        f"- note : {reference['note']}",
        "",
        "## Écart aux objectifs NFR2",
        "",
        "| condition | cible | mesuré | écart | atteint |",
        "|---|---|---|---|---|",
    ]
    for gap in comparison["nfr2"]["constrained_gap"]:
        if gap["measured"] is None:
            lines.append(f"| {gap['condition']} | {gap['target']:.2f} | — | — | — |")
            continue
        lines.append(
            f"| {gap['condition']} | {gap['target']:.2f} | {gap['measured']:.4f} | "
            f"{gap['gap']:+.4f} | {'✅' if gap['meets_target'] else '❌'} |"
        )

    rates = comparison["decision_rates"]
    lines += [
        "",
        "## Taux de décision",
        "",
        "| taux | glouton | contraint |",
        "|---|---|---|",
        f"| rejet | {rates['greedy']['rejection_rate']:.4f} | "
        f"{rates['constrained']['rejection_rate']:.4f} |",
        f"| fausse acceptation | {rates['greedy']['false_acceptance_rate']:.4f} | "
        f"{rates['constrained']['false_acceptance_rate']:.4f} |",
        f"| confirmation | {rates['greedy']['confirmation_rate']:.4f} | "
        f"{rates['constrained']['confirmation_rate']:.4f} |",
        f"| acceptation correcte | {rates['greedy']['correct_acceptance_rate']:.4f} | "
        f"{rates['constrained']['correct_acceptance_rate']:.4f} |",
        "",
    ]
    return "\n".join(lines) + "\n"


def _evaluate_side(
    entries,
    hypotheses_path: Path,
    manifest_path: Path,
    settings,
    split: str,
    top_confusions: int,
):
    """Évalue un jeu d'hypothèses via le harnais 5.2 (mode rejeu, sans GPU).

    L'empreinte portée par le rapport est celle du **manifest** (vérité terrain
    partagée par les deux côtés), pas celle du fichier d'hypothèses.
    """

    hypotheses = load_hypotheses(hypotheses_path)
    result = evaluate(entries, replay_source(hypotheses), settings, top_confusions=top_confusions)
    return build_report(
        result,
        manifest_path=manifest_path,
        settings=settings,
        asr_mode="replay",
        latency_source="replay",
        split=split,
    )


def _run(args: argparse.Namespace) -> int:
    try:
        entries = read_manifest(args.manifest)
    except (OSError, ValueError, KeyError) as exc:
        print(f"Manifest introuvable ou invalide : {args.manifest} ({exc})", file=sys.stderr)
        return 2

    if args.split != "all":
        entries = [entry for entry in entries if entry.split == args.split]
    if not entries:
        print(f"Aucune entrée pour le split « {args.split} ».", file=sys.stderr)
        return 2

    settings = get_settings()
    try:
        greedy = _evaluate_side(
            entries, args.greedy, args.manifest, settings, args.split, args.top_confusions
        )
        constrained = _evaluate_side(
            entries, args.constrained, args.manifest, settings, args.split, args.top_confusions
        )
    except (EvaluationError, OSError, KeyError, ValueError) as exc:
        print(f"Évaluation impossible (fail-closed) : {exc}", file=sys.stderr)
        return 2

    comparison = build_comparison(greedy, constrained, split=args.split)
    # Traçabilité des deux sources d'hypothèses comparées.
    comparison["reports"]["greedy"]["hypotheses"] = args.greedy.name
    comparison["reports"]["constrained"]["hypotheses"] = args.constrained.name

    json_path = args.out.with_suffix(".json")
    md_path = args.out.with_suffix(".md")
    atomic_write_text(
        json_path, json.dumps(comparison, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    )
    atomic_write_text(md_path, comparison_to_markdown(comparison))

    overall = comparison["overall"]
    print(
        f"glouton {overall['greedy']:.4f} → contraint {overall['constrained']:.4f} "
        f"({overall['delta']:+.4f}) [split={args.split}] → {json_path.name}, {md_path.name}"
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Comparaison glouton vs contraint (story 5.6).")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--greedy", type=Path, required=True, help="JSONL hypothèses gloutonnes.")
    parser.add_argument(
        "--constrained", type=Path, required=True, help="JSONL hypothèses contraintes."
    )
    parser.add_argument("--split", default="test", help="test | dev | all (défaut : test)")
    parser.add_argument("--top-confusions", type=int, default=20)
    parser.add_argument(
        "--out",
        type=Path,
        default=_REPO_ROOT / "docs" / "qa" / "benchmarks" / "decoding-greedy-vs-constrained",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    return _run(_build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
