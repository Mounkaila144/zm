#!/usr/bin/env python
"""Profilage **par étapes** du chemin ASR complet, sur le corpus de performance.

Le serveur ne chronomètre aujourd'hui que deux blocs : « modèle » et « décodage ».
C'est trop grossier pour décider quoi optimiser — « modèle » agrège le
rééchantillonnage, la construction du lot, le passage avant et le rapatriement
des logits ; « décodage » agrège le log-softmax, la recherche en faisceau et le
rescoring exact, dont les coûts n'ont ni le même ordre de grandeur ni les mêmes
leviers.

Ce script ventile chaque étape séparément, et **écrit les logits sur disque**
(``--dump-logits``). Ce second point est décisif pour la suite : une fois les
logits capturés, tout le travail sur le décodeur se valide hors ligne, à
l'identique et en quelques secondes, sans jamais recharger les 2 Go du modèle ni
perturber la production.

Usage :
    asrenv/bin/python scripts/bench/profile_asr.py --repeats 3 --dump-logits out/
"""

from __future__ import annotations

import argparse
import json
import resource
import statistics
import sys
import time
import wave
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services" / "asr"))

CORPUS = REPO / "dataset" / "benchmark" / "perf"


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


class StagedAsr:
    """Réplique le chemin de ``LocalAsr`` en chronométrant chaque étape.

    Volontairement construit sur les **mêmes** appels que le serveur (mêmes
    membres du pipeline ``omnilingual_asr``, même décodeur) : un profil obtenu
    sur un chemin différent de celui de la production ne prouverait rien.
    """

    def __init__(self, *, grammar_kind: str, beam_width: int, threads: int) -> None:
        import torch

        torch.set_num_threads(threads)
        from app.decoding import DecoderConfig  # noqa: PLC0415
        from local_server import CTC_MODEL, LocalAsr  # noqa: PLC0415

        self.model_name = CTC_MODEL
        started = time.perf_counter()
        self._asr = LocalAsr(
            grammar_kind=grammar_kind,
            device="cpu",
            config=DecoderConfig(beam_width=beam_width),
        )
        self.load_s = time.perf_counter() - started
        self.threads = threads

    # -- étapes ------------------------------------------------------------

    def stages(self, wav_bytes: bytes) -> tuple[dict[str, float], np.ndarray, object]:
        import torch
        from app import decoding as dec  # noqa: PLC0415
        from fairseq2.data.data_pipeline import DataPipeline, read_sequence
        from fairseq2.nn.batch_layout import BatchLayout

        t: dict[str, float] = {}
        asr = self._asr

        mark = time.perf_counter()
        import io

        with wave.open(io.BytesIO(wav_bytes), "rb") as reader:
            sample_rate = reader.getframerate()
            frames_raw = reader.readframes(reader.getnframes())
        samples = np.frombuffer(frames_raw, dtype="<i2").astype("float32") / 32768.0
        t["wav_lecture"] = time.perf_counter() - mark

        mark = time.perf_counter()
        builder = DataPipeline.zip(
            [
                asr._pipeline._build_audio_wavform_pipeline(  # noqa: SLF001
                    [{"waveform": samples, "sample_rate": sample_rate}]
                ).and_return(),
                read_sequence([None]).and_return(),
            ]
        )
        batch = next(
            iter(
                builder.bucket(1).map(asr._pipeline._create_batch_simple).and_return()
            )  # noqa: SLF001
        )
        seqs = batch.source_seqs.to(device=asr._device, dtype=asr._dtype)  # noqa: SLF001
        layout = BatchLayout(seqs.shape, seq_lens=batch.source_seq_lens, device=seqs.device)
        t["preparation_lot"] = time.perf_counter() - mark

        mark = time.perf_counter()
        with torch.inference_mode():
            logits_t, out_layout = asr._pipeline.model(seqs, layout)  # noqa: SLF001
        t["inference_torch"] = time.perf_counter() - mark

        mark = time.perf_counter()
        length = int(list(out_layout.seq_lens)[0])
        logits = logits_t[0, :length].detach().float().cpu().numpy()
        t["transfert_logits"] = time.perf_counter() - mark

        # -- décodage, ventilé -------------------------------------------
        mark = time.perf_counter()
        dec.log_softmax(logits)
        t["log_softmax"] = time.perf_counter() - mark

        # Recherche en faisceau seule : on rejoue `decode` avec le rescoring
        # exact désactivé, puis on mesure le rescoring par différence. C'est la
        # seule façon d'isoler les deux sans dupliquer la logique du décodeur.
        from app.decoding import ConstrainedCtcDecoder, DecoderConfig  # noqa: PLC0415

        cfg = asr._decoder.config  # noqa: SLF001
        cheap = ConstrainedCtcDecoder.__new__(ConstrainedCtcDecoder)
        cheap._config = DecoderConfig(  # noqa: SLF001
            beam_width=cfg.beam_width,
            nbest=cfg.nbest,
            blank_id=cfg.blank_id,
            length_exponent=cfg.length_exponent,
            min_frames_per_token=cfg.min_frames_per_token,
            exact_rescore=False,
            reject_threshold=cfg.reject_threshold,
        )
        cheap._automaton = asr._decoder._automaton  # noqa: SLF001
        mark = time.perf_counter()
        cheap.decode(logits)
        t["faisceau_sans_rescore"] = time.perf_counter() - mark

        mark = time.perf_counter()
        result = asr._decoder.decode(logits)  # noqa: SLF001
        full_decode = time.perf_counter() - mark
        t["decodage_total"] = full_decode
        t["rescore_exact"] = max(0.0, full_decode - t["faisceau_sans_rescore"])

        mark = time.perf_counter()
        from app.transcription import build_transcribe_payload  # noqa: PLC0415

        payload = build_transcribe_payload(result, model_version=self.model_name, latency_ms=0)
        json.dumps(payload)
        t["serialisation"] = time.perf_counter() - mark

        t["_frames"] = float(logits.shape[0])
        t["_vocab"] = float(logits.shape[1])
        t["_audio_s"] = len(samples) / 16_000.0
        return t, logits, payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--beam-width", type=int, default=64)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--grammar", default="expressions")
    parser.add_argument("--dump-logits", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None, help="JSON des mesures")
    parser.add_argument("--only", default=None, help="filtre sur le nom d'énoncé")
    args = parser.parse_args(argv)

    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    if args.only:
        manifest = [e for e in manifest if args.only in e["name"]]

    asr = StagedAsr(grammar_kind=args.grammar, beam_width=args.beam_width, threads=args.threads)
    print(
        f"modèle chargé en {asr.load_s:.1f}s · torch threads={args.threads} · "
        f"beam={args.beam_width}"
    )
    if args.dump_logits:
        args.dump_logits.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, object]] = []
    for entry in manifest:
        wav_bytes = (CORPUS / entry["file"]).read_bytes()
        runs: list[dict[str, float]] = []
        payload = None
        logits = None
        for _ in range(args.repeats):
            timings, logits, payload = asr.stages(wav_bytes)
            runs.append(timings)
        if args.dump_logits and logits is not None:
            np.save(args.dump_logits / f"{entry['name']}.npy", logits.astype(np.float32))
        keys = [k for k in runs[0] if not k.startswith("_")]
        median = {k: statistics.median(r[k] for r in runs) * 1000.0 for k in keys}
        record = {
            "name": entry["name"],
            "condition": entry["condition"],
            "audio_s": round(runs[0]["_audio_s"], 2),
            "frames": int(runs[0]["_frames"]),
            "vocab": int(runs[0]["_vocab"]),
            "expected_text": entry["expected_text"],
            "text": payload["text"] if payload else "",
            "acoustic_score": round(payload["acoustic_score"], 3) if payload else 0.0,
            "ms": {k: round(v, 1) for k, v in median.items()},
        }
        records.append(record)
        ms = record["ms"]
        print(
            f"  {entry['name']:14s} {record['audio_s']:5.2f}s T={record['frames']:4d} "
            f"| prep {ms['preparation_lot']:6.0f} infer {ms['inference_torch']:7.0f} "
            f"| lsm {ms['log_softmax']:5.0f} faisceau {ms['faisceau_sans_rescore']:7.0f} "
            f"rescore {ms['rescore_exact']:7.0f} | « {record['text'][:44]} »",
            flush=True,
        )

    print(f"\nRSS max : {_peak_rss_mb():.0f} Mo")
    if args.out:
        args.out.write_text(
            json.dumps(
                {
                    "threads": args.threads,
                    "beam_width": args.beam_width,
                    "peak_rss_mb": round(_peak_rss_mb(), 1),
                    "records": records,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"mesures → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
