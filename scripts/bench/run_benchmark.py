#!/usr/bin/env python
"""Harnais d'évaluation — Exact Number Accuracy + matrice de confusions (story 5.2).

Rejoue le pipeline complet (ASR → normalisation → parsing → confiance → politique)
sur le corpus 5.1 et exporte un rapport versionné (`.json` + `.md`) dans
`docs/qa/benchmarks/`.

Deux sources ASR (jamais un modèle en dur, NFR9) :

    # A) Rejeu d'hypothèses pré-calculées (aucun GPU, reproductible) :
    uv run python scripts/bench/run_benchmark.py \
        --manifest dataset/manifests/benchmark.jsonl \
        --hypotheses dataset/benchmark/hypotheses/ctc.jsonl \
        --split test --out docs/qa/benchmarks/benchmark-test

    # B) Passe réelle via un recognizer configuré (après story 5.3), avec dump
    #    d'hypothèses réutilisable en rejeu :
    uv run python scripts/bench/run_benchmark.py \
        --manifest dataset/manifests/benchmark.jsonl \
        --asr-mode ctc --audio-root dataset/benchmark \
        --dump-hypotheses dataset/benchmark/hypotheses/ctc.jsonl \
        --split test --out docs/qa/benchmarks/benchmark-test

Fail-closed : manifest introuvable/invalide, split vide, ou entrées inexploitables
sans `--allow-partial` → code de sortie non nul.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BENCH_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BENCH_DIR.parents[1]
_API_ROOT = _REPO_ROOT / "services" / "api"
for _path in (_BENCH_DIR, _API_ROOT):
    if _path.is_dir() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from app.asr.factory import get_recognizer  # noqa: E402
from app.config import get_settings  # noqa: E402
from benchmark_corpus import read_manifest  # noqa: E402
from evaluation import (  # noqa: E402
    CapturingSource,
    EvaluationError,
    build_report,
    evaluate,
    load_hypotheses,
    recognizer_source,
    replay_source,
    write_hypotheses,
    write_report,
)

_DEFAULT_OUT_DIR = _REPO_ROOT / "docs" / "qa" / "benchmarks"


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def _run(args: argparse.Namespace) -> int:
    try:
        entries = read_manifest(args.manifest)
    except (OSError, ValueError, KeyError) as exc:
        return _fail(f"Manifest introuvable ou invalide : {args.manifest} ({exc})")

    if args.split != "all":
        entries = [entry for entry in entries if entry.split == args.split]
    if not entries:
        return _fail(f"Aucune entrée pour le split « {args.split} ».")

    settings = get_settings()
    capturing: CapturingSource | None = None

    if args.hypotheses is not None:
        hypotheses = load_hypotheses(args.hypotheses)
        if args.allow_partial:
            entries = [e for e in entries if e.audio_path in hypotheses]
        source = replay_source(hypotheses)
        asr_mode, latency_source = "replay", "replay"
    else:
        if args.audio_root is None:
            return _fail("--audio-root est requis avec --asr-mode.")
        settings = settings.model_copy(update={"ASR_MODE": args.asr_mode})
        recognizer = get_recognizer(settings)
        if args.allow_partial:
            entries = [e for e in entries if (args.audio_root / e.audio_path).is_file()]
        source = recognizer_source(recognizer, args.audio_root)
        if args.dump_hypotheses is not None:
            capturing = CapturingSource(source)
            source = capturing
        asr_mode, latency_source = args.asr_mode, "live"

    if not entries:
        return _fail("Aucune entrée exploitable après filtrage (--allow-partial).")

    try:
        result = evaluate(entries, source, settings, top_confusions=args.top_confusions)
    except EvaluationError as exc:
        return _fail(f"Entrée inexploitable (fail-closed) : {exc}. Utiliser --allow-partial ?")

    if capturing is not None and args.dump_hypotheses is not None:
        write_hypotheses(args.dump_hypotheses, capturing.captured)

    report = build_report(
        result,
        manifest_path=args.manifest,
        settings=settings,
        asr_mode=asr_mode,
        latency_source=latency_source,
        split=args.split,
    )
    json_path, md_path = write_report(args.out, report)
    print(
        f"Exact Number Accuracy = {result.accuracy:.4f} ({result.correct}/{result.total}) "
        f"[split={args.split}] → {json_path.name}, {md_path.name}"
    )
    if result.expression_total:
        print(
            f"Exact Expression Accuracy = {result.exact_expression_accuracy:.4f} "
            f"({result.expression_correct}/{result.expression_total})"
        )
    if result.refusals.total:
        # Un résultat inventé sur un cas impossible est la pire défaillance
        # possible : il est affiché même quand tout le reste va bien.
        print(
            f"Refus correct = {result.refusals.correct_rate:.4f} "
            f"({result.refusals.correct}/{result.refusals.total}) · "
            f"résultat inventé = {result.refusals.invented_rate:.4f}"
        )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Harnais Exact Number Accuracy (story 5.2).")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--split", default="test", help="test | dev | all (défaut : test)")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--hypotheses", type=Path, help="JSONL d'hypothèses ASR (mode rejeu).")
    source.add_argument("--asr-mode", choices=("mock", "ctc", "llm"), help="Recognizer configuré.")
    parser.add_argument("--audio-root", type=Path, default=None)
    parser.add_argument("--dump-hypotheses", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT_DIR / "benchmark")
    parser.add_argument("--top-confusions", type=int, default=20)
    parser.add_argument("--allow-partial", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    return _run(_build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
