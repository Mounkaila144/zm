#!/usr/bin/env python
"""Constitution reproductible du corpus de benchmark (story 5.1).

Sans GPU : planification, assemblage et validation d'un corpus d'évaluation avec
split strict par locuteur. Trois sous-commandes :

    # 1) Générer le plan d'enregistrement (quoi enregistrer, pour ≥ 100 audios) :
    uv run python scripts/bench/build_benchmark_corpus.py plan \
        --speakers spk01 spk02 spk03 spk04 \
        --out dataset/benchmark/recording_plan.jsonl

    # 1 bis) Générer le plan d'ÉNONCÉS D'OPÉRATIONS (story 6.1) — énoncés
    #        complets, jamais des opérateurs isolés, cas hors domaine inclus :
    uv run python scripts/bench/build_benchmark_corpus.py plan-expressions \
        --speakers spk01 spk02 spk03 spk04 \
        --out dataset/benchmark/expression_recording_plan.jsonl

    # 2) Assembler le manifest versionné depuis l'index des audios enregistrés :
    uv run python scripts/bench/build_benchmark_corpus.py build \
        --source dataset/benchmark/source_index.jsonl \
        --benchmark-dir dataset/benchmark \
        --out dataset/manifests/benchmark.jsonl

    # 3) Valider l'intégrité d'un manifest (vérité terrain, non-fuite, couverture) :
    uv run python scripts/bench/build_benchmark_corpus.py validate \
        --manifest dataset/manifests/benchmark.jsonl

L'audio brut/enregistré reste hors Git ; seuls le manifest et les scripts sont
versionnés. Aucune donnée non consentie dans le corpus (voir
``dataset/benchmark/README.md``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Rend le module cœur importable même sans installation particulière.
_BENCH_DIR = Path(__file__).resolve().parent
if str(_BENCH_DIR) not in sys.path:
    sys.path.insert(0, str(_BENCH_DIR))

import zarma_numbers  # noqa: E402
from benchmark_corpus import (  # noqa: E402
    DEFAULT_SPLIT_SEED,
    build_expression_recording_plan,
    build_manifest,
    build_recording_plan,
    expression_plan_dict,
    plan_dict,
    read_manifest,
    read_source,
    select_target_expressions,
    select_target_numbers,
    validate_manifest,
    write_jsonl,
    write_manifest,
)


def _cmd_plan(args: argparse.Namespace) -> int:
    lexicon = zarma_numbers.load_lexicon()
    targets = select_target_numbers(lexicon)
    plan = build_recording_plan(targets, args.speakers)
    write_jsonl(args.out, [plan_dict(item) for item in plan])
    tags = {tag for item in plan for tag in item.tags}
    print(
        f"Plan écrit : {len(plan)} consigne(s) pour {len(args.speakers)} locuteur(s) "
        f"[couverture : {', '.join(sorted(tags))}] → {args.out}"
    )
    return 0


def _cmd_plan_expressions(args: argparse.Namespace) -> int:
    lexicon = zarma_numbers.load_lexicon()
    targets = select_target_expressions(lexicon)
    plan = build_expression_recording_plan(targets, args.speakers)
    write_jsonl(args.out, [expression_plan_dict(item) for item in plan])

    tags = {tag for item in plan for tag in item.tags}
    refusals = sum(1 for item in plan if item.expected_refusal is not None)
    unresolved = sorted(
        name for name, operator in lexicon.operators.items() if not operator.resolved
    )
    print(
        f"Plan d'expressions écrit : {len(plan)} consigne(s) pour "
        f"{len(args.speakers)} locuteur(s), dont {refusals} cas hors domaine "
        f"[couverture : {', '.join(sorted(tags))}] → {args.out}"
    )
    if unresolved:
        print(
            f"⚠️  Opérateurs non couverts (forme zarma non validée) : {', '.join(unresolved)}. "
            "Compléter docs/lexique-operateurs-a-valider.md les fera apparaître ici.",
            file=sys.stderr,
        )
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    rows = read_source(args.source)
    result = build_manifest(
        rows,
        seed=args.seed,
        audio_root=args.benchmark_dir,
        allow_partial=args.allow_partial,
    )
    for error in result.errors:
        print(f"  exclu {error.audio_path} : {error.reason}", file=sys.stderr)
    if not result.written:
        print("Manifest NON écrit (fail-closed) : entrées invalides.", file=sys.stderr)
        return 1
    write_manifest(args.out, result.entries)
    report = validate_manifest(
        result.entries,
        min_audios=args.min_audios,
        min_speakers=args.min_speakers,
    )
    print(
        f"Manifest écrit : {len(result.entries)} audio(s), {report.speakers} locuteur(s), "
        f"splits={report.per_split}, couverture={report.per_tag} → {args.out}"
    )
    return 0 if report.ok else 2


def _cmd_validate(args: argparse.Namespace) -> int:
    entries = read_manifest(args.manifest)
    report = validate_manifest(
        entries,
        min_audios=args.min_audios,
        min_speakers=args.min_speakers,
    )
    print(
        f"{report.total_audios} audio(s), {report.speakers} locuteur(s), "
        f"splits={report.per_split}, conditions={report.per_condition}, "
        f"couverture={report.per_tag}"
    )
    if report.leaking_speakers:
        print(f"FUITE DE LOCUTEUR : {report.leaking_speakers}", file=sys.stderr)
    for problem in report.problems:
        print(f"  problème : {problem}", file=sys.stderr)
    return 0 if report.ok else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Corpus de benchmark (split par locuteur).")
    sub = parser.add_subparsers(dest="command", required=True)

    plan_cmd = sub.add_parser("plan", help="Générer le plan d'enregistrement.")
    plan_cmd.add_argument("--speakers", nargs="+", required=True, help="Labels de locuteurs.")
    plan_cmd.add_argument("--out", type=Path, required=True)
    plan_cmd.set_defaults(func=_cmd_plan)

    expressions_cmd = sub.add_parser(
        "plan-expressions",
        help="Générer le plan d'enregistrement des ÉNONCÉS D'OPÉRATIONS (story 6.1).",
    )
    expressions_cmd.add_argument("--speakers", nargs="+", required=True)
    expressions_cmd.add_argument("--out", type=Path, required=True)
    expressions_cmd.set_defaults(func=_cmd_plan_expressions)

    build_cmd = sub.add_parser("build", help="Assembler le manifest depuis l'index source.")
    build_cmd.add_argument("--source", type=Path, required=True)
    build_cmd.add_argument("--out", type=Path, required=True)
    build_cmd.add_argument("--benchmark-dir", type=Path, default=None)
    build_cmd.add_argument("--seed", default=DEFAULT_SPLIT_SEED)
    build_cmd.add_argument("--allow-partial", action="store_true")
    build_cmd.add_argument("--min-audios", type=int, default=100)
    build_cmd.add_argument("--min-speakers", type=int, default=3)
    build_cmd.set_defaults(func=_cmd_build)

    validate_cmd = sub.add_parser("validate", help="Valider l'intégrité d'un manifest.")
    validate_cmd.add_argument("--manifest", type=Path, required=True)
    validate_cmd.add_argument("--min-audios", type=int, default=100)
    validate_cmd.add_argument("--min-speakers", type=int, default=3)
    validate_cmd.set_defaults(func=_cmd_validate)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
