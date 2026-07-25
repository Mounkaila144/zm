#!/usr/bin/env python
"""Transcription **locale** des audios de benchmark via Omnilingual ASR (outillage 5.4).

S'exécute dans un environnement **isolé** (omnilingual-asr + torch), séparé du
projet API — voir `scripts/bench/README-local-asr.md`. Il produit un **dump
d'hypothèses JSONL** au format attendu par le harnais 5.2
(`run_benchmark.py --hypotheses …`), de sorte que les métriques se recalculent
**sans recharger le modèle** (mode rejeu reproductible).

Ne dépend **que** de `omnilingual_asr` + stdlib (jamais `zarma_numbers` ni `app.*`)
afin de rester importable dans l'env ASR minimal.

⚠️ Limite connue : l'API haut-niveau `ASRInferencePipeline.transcribe` ne renvoie
que le **texte** (pas de score acoustique ni d'alternatives). On écrit donc un
`acoustic_score` fixe configurable (`--acoustic-score`, défaut 1.0) et des
`candidates` vides. L'**Exact Number Accuracy** (métrique de décision) n'en dépend
pas ; en revanche les taux accept/confirm/repeat sont à interpréter avec cette
réserve, à documenter dans le rapport de décision.

Usage (dans l'env ASR isolé) :
    asrenv/bin/python scripts/bench/transcribe_local.py \
        --manifest dataset/manifests/benchmark.jsonl \
        --audio-root dataset/benchmark \
        --model ctc \
        --out dataset/benchmark/hypotheses/ctc.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from uuid import uuid4

# Raccourcis de modèle → (model_card, lang). CTC : sans lang ; LLM : dje_Latn.
MODELS: dict[str, tuple[str, list[str] | None]] = {
    "ctc": ("omniASR_CTC_300M_v2", None),
    "llm": ("omniASR_LLM_300M_v2", ["dje_Latn"]),
}


def _read_audio_paths(manifest: Path) -> list[str]:
    """Extrait les ``audio_path`` du manifest 5.1 sans importer ``zarma_numbers``."""

    paths: list[str] = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.strip():
            paths.append(json.loads(line)["audio_path"])
    return paths


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Transcription locale Omnilingual ASR → hypothèses."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--audio-root", type=Path, required=True)
    parser.add_argument("--model", choices=sorted(MODELS), default="ctc")
    parser.add_argument("--model-card", default=None, help="Surcharge le model_card exact.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--acoustic-score", type=float, default=1.0)
    parser.add_argument("--limit", type=int, default=0, help="0 = tout ; sinon N premiers.")
    args = parser.parse_args(argv)

    model_card, lang = MODELS[args.model]
    if args.model_card:
        model_card = args.model_card

    # Import tardif : n'échoue pas si l'utilisateur ne fait qu'un --help.
    from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline

    print(f"Chargement du modèle {model_card} …", flush=True)
    pipeline = ASRInferencePipeline(model_card=model_card)

    audio_paths = _read_audio_paths(args.manifest)
    if args.limit:
        audio_paths = audio_paths[: args.limit]

    records: list[dict] = []
    for index, audio_path in enumerate(audio_paths, 1):
        source = str(args.audio_root / audio_path)
        started = time.perf_counter()
        kwargs = {} if lang is None else {"lang": lang}
        text = pipeline.transcribe([source], **kwargs)[0]
        latency_ms = int((time.perf_counter() - started) * 1000)
        records.append(
            {
                "audio_path": audio_path,
                "text": text,
                "acoustic_score": args.acoustic_score,
                "candidates": [],
                "latency_ms": latency_ms,
                "model_version": model_card,
            }
        )
        print(
            f"  [{index}/{len(audio_paths)}] {audio_path} → {text!r} ({latency_ms} ms)",
            flush=True,
        )

    _write_jsonl(args.out, records)
    print(f"Écrit {len(records)} hypothèse(s) → {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
