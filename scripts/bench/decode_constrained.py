#!/usr/bin/env python
"""Passe de décodage **contraint** sur un corpus audio (story 5.6, tasks 5 & 6).

Produit, en une passe, les trois artefacts dont dépendent les autres outils :

1. ``--out`` : un JSONL d'**hypothèses** au format du harnais 5.2, rejouable
   sans GPU par ``run_benchmark.py --hypotheses`` puis ``compare_decoding.py`` ;
2. ``--dump-observations`` : les **confiances de décodage** étiquetées, entrée de
   ``calibrate_rejection.py`` (task 3) ;
3. ``--dump-logits`` : quelques **fixtures de logits réels** (``.npz`` compressé)
   pour tester le décodeur en CI **sans modèle ni GPU** (task 6).

⚠️ Ce script est le **seul** de la chaîne à exiger l'environnement ASR lourd
(torch + ``omnilingual_asr``) : il s'exécute dans l'environnement isolé décrit
par ``scripts/bench/README-local-asr.md``, **jamais** en CI.

    export DYLD_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_LIBRARY_PATH
    asrenv/bin/python scripts/bench/decode_constrained.py \\
        --manifest dataset/manifests/benchmark.jsonl \\
        --audio-root ~/Music \\
        --out dataset/benchmark/hypotheses/ctc-constrained.jsonl \\
        --dump-observations dataset/benchmark/rejection/dev-observations.jsonl \\
        --dump-logits services/asr/tests/fixtures

Le paquet ``zarma_numbers`` n'étant pas installé dans l'environnement ASR, ce
script insère les chemins nécessaires dans ``sys.path`` (source unique conservée :
la grammaire vient bien du paquet, jamais réécrite).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import wave
from pathlib import Path

_BENCH_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BENCH_DIR.parents[1]
_PACKAGE_SRC = _REPO_ROOT / "packages" / "zarma_numbers" / "src"
_ASR_APP = _REPO_ROOT / "services" / "asr" / "app"
for _path in (_BENCH_DIR, _PACKAGE_SRC, _ASR_APP):
    if _path.is_dir() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import numpy as np  # noqa: E402
from decoding import (  # noqa: E402
    ConstrainedCtcDecoder,
    DecoderConfig,
    build_token_lexicon,
)
from zarma_numbers.grammar import load_grammar  # noqa: E402

CTC_MODEL = "omniASR_CTC_300M_v2"


def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    """Lit un WAV PCM16 mono en float32 [-1, 1]."""

    with wave.open(str(path), "rb") as reader:
        sample_rate = reader.getframerate()
        frames = reader.readframes(reader.getnframes())
    samples = np.frombuffer(frames, dtype="<i2").astype("float32") / 32768.0
    return samples, sample_rate


def _load_pipeline():
    """Charge le pipeline Omnilingual CTC (import tardif : hors CI)."""

    import torch
    from omnilingual_asr.models.inference import pipeline as P

    return P, torch, P.ASRInferencePipeline(model_card=CTC_MODEL, device="cpu", dtype=torch.float32)


def _logits_extractor(module, torch, pipeline):
    """Retourne ``samples -> logits (T, V)`` en capturant la sortie du modèle.

    Le pipeline officiel calcule les logits puis les jette (``argmax``). En
    production le service appelle ``self.model(...)`` directement ; ici, sur un
    outil de mesure hors ligne, on garde la capture par interception — c'est
    l'usage documenté en Annexe A §1, assumé comme outillage de benchmark.
    """

    captured: dict[str, object] = {}
    original = module.ASRInferencePipeline._apply_model_wav2vec2asr

    def patched(self, batch):
        layout = module.BatchLayout(
            batch.source_seqs.shape,
            seq_lens=batch.source_seq_lens,
            device=batch.source_seqs.device,
        )
        logits, out_layout = self.model(batch.source_seqs, layout)
        captured["logits"] = logits.detach().float().cpu()
        captured["lens"] = list(out_layout.seq_lens)
        return original(self, batch)

    module.ASRInferencePipeline._apply_model_wav2vec2asr = patched

    def extract(audio_path: Path) -> tuple[np.ndarray, str]:
        captured.clear()
        greedy = pipeline.transcribe([str(audio_path)])[0]
        logits = captured["logits"][0][: captured["lens"][0]]
        return logits.numpy(), greedy

    return extract


def _token_encoder(pipeline):
    """Encodeur du tokenizer, tokens spéciaux bas filtrés (Annexe A §2)."""

    encoder = pipeline.tokenizer.create_encoder()

    def encode(text: str) -> list[int]:
        ids = encoder(text)
        ids = ids.tolist() if hasattr(ids, "tolist") else list(ids)
        return [int(i) for i in ids if int(i) > 3]

    return encode


def _manifest_rows(manifest: Path) -> list[dict]:
    rows = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _run(args: argparse.Namespace) -> int:
    rows = _manifest_rows(args.manifest)
    if args.split != "all":
        rows = [row for row in rows if row.get("split") == args.split]
    if not rows:
        print(f"Aucune entrée pour le split « {args.split} ».", file=sys.stderr)
        return 2

    module, torch, pipeline = _load_pipeline()
    extract = _logits_extractor(module, torch, pipeline)
    grammar = load_grammar()
    lexicon = build_token_lexicon(
        grammar,
        _token_encoder(pipeline),
        separator=tuple(int(i) for i in args.separator_ids),
        blank_id=args.blank_id,
    )
    decoder = ConstrainedCtcDecoder(
        grammar,
        lexicon,
        DecoderConfig(
            beam_width=args.beam_width,
            nbest=args.nbest,
            blank_id=args.blank_id,
            length_exponent=args.length_exponent,
            min_frames_per_token=args.min_frames_per_token,
            reject_threshold=args.reject_threshold,
        ),
    )

    hypotheses: list[dict] = []
    observations: list[dict] = []
    greedy_rows: list[dict] = []
    dumped_logits = 0

    for row in rows:
        audio_path = args.audio_root / row["audio_path"]
        if not audio_path.is_file():
            print(f"audio manquant : {row['audio_path']}", file=sys.stderr)
            if not args.allow_partial:
                return 2
            continue

        started = time.perf_counter()
        logits, greedy_text = extract(audio_path)
        result = decoder.decode(logits)
        latency_ms = int((time.perf_counter() - started) * 1000)

        best = result.best
        hypotheses.append(
            {
                "audio_path": row["audio_path"],
                "text": "" if result.rejected or best is None else best.text,
                "acoustic_score": round(result.confidence, 6),
                "candidates": [
                    {"text": h.text, "score": round(h.confidence, 6), "number": None}
                    for h in result.hypotheses[1:]
                ],
                "latency_ms": latency_ms,
                "model_version": CTC_MODEL,
            }
        )
        greedy_rows.append(
            {
                "audio_path": row["audio_path"],
                "text": greedy_text,
                "acoustic_score": 1.0,  # le pipeline officiel n'expose aucun score
                "candidates": [],
                "latency_ms": latency_ms,
                "model_version": CTC_MODEL,
            }
        )
        observations.append(
            {
                "audio_path": row["audio_path"],
                "split": row.get("split", "dev"),
                "is_numeric": bool(row.get("is_numeric", True)),
                "confidence": round(result.confidence, 6),
            }
        )

        if args.dump_logits is not None and dumped_logits < args.max_logits:
            args.dump_logits.mkdir(parents=True, exist_ok=True)
            name = Path(row["audio_path"]).stem
            np.savez_compressed(
                args.dump_logits / f"{name}.npz",
                logits=logits.astype(np.float16),
                expected_number=np.int64(row.get("expected_number", -1)),
                expected_prompt=str(row.get("expected_prompt", "")),
                model_version=CTC_MODEL,
            )
            dumped_logits += 1

    _write_jsonl(args.out, hypotheses)
    if args.dump_greedy is not None:
        _write_jsonl(args.dump_greedy, greedy_rows)
    if args.dump_observations is not None:
        _write_jsonl(args.dump_observations, observations)

    accepted = sum(1 for h in hypotheses if h["text"])
    print(
        f"{len(hypotheses)} audios décodés ({accepted} acceptés, "
        f"{len(hypotheses) - accepted} rejetés) → {args.out}"
    )
    if args.dump_logits is not None:
        print(f"{dumped_logits} fixtures de logits → {args.dump_logits}")
    return 0


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Décodage contraint hors ligne (story 5.6).")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--audio-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--split", default="all")
    parser.add_argument("--dump-greedy", type=Path, default=None)
    parser.add_argument("--dump-observations", type=Path, default=None)
    parser.add_argument("--dump-logits", type=Path, default=None)
    parser.add_argument("--max-logits", type=int, default=4)
    parser.add_argument("--allow-partial", action="store_true")
    # Paramètres du décodeur (mêmes défauts que DecoderConfig / AsrSettings).
    parser.add_argument("--beam-width", type=int, default=64)
    parser.add_argument("--nbest", type=int, default=5)
    parser.add_argument("--blank-id", type=int, default=0)
    parser.add_argument("--length-exponent", type=float, default=1.0)
    parser.add_argument("--min-frames-per-token", type=float, default=1.0)
    parser.add_argument("--reject-threshold", type=float, default=0.0)
    parser.add_argument("--separator-ids", type=int, nargs="*", default=())
    return parser


def main(argv: list[str] | None = None) -> int:
    return _run(_build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
