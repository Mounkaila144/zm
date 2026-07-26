#!/usr/bin/env python
"""Tableau avant/après de la latence ASR, sur le corpus de performance.

Trois variantes sont exécutées **en alternance énoncé par énoncé**, dans un seul
processus. C'est le point méthodologique important : les mesures précédentes ont
montré jusqu'à 2,9× d'écart sur le même énoncé selon le moment, sur ce VPS à
4 vCPU partagé avec l'API, Redis et PostgreSQL. Mesurer une variante puis
l'autre attribuerait à la variante toute dérive de charge survenue entre les
deux. En alternant, une perturbation frappe les trois également.

Variantes :

- ``reference``  : ce qui est déployé aujourd'hui — 4 fils, pas d'élagage de
  silence, décodeur d'origine (chargé depuis un fichier séparé).
- ``optimise``   : la proposition — 2 fils, élagage des bords muets, décodeur
  optimisé.
- ``opt_4fils``  : identique à ``optimise`` mais 4 fils, pour **isoler** la part
  du réglage de threads dans le gain total.

Chaque variante rapporte, par énoncé et en agrégé : durée audio, temps modèle,
temps décodage, total, texte reconnu, confiance, p50 et p95, plus le RSS maximal
du processus.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import resource
import statistics
import sys
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services" / "asr"))
CORPUS = REPO / "dataset" / "benchmark" / "perf"


@dataclass
class Variant:
    name: str
    threads: int
    use_vad: bool
    decoder_module: Path | None  # None = décodeur courant


def _percentile(values: list[float], q: float) -> float:
    """Percentile par interpolation linéaire (méthode de ``numpy.percentile``)."""
    if not values:
        return 0.0
    return float(np.percentile(np.asarray(values, dtype=np.float64), q))


def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as reader:
        rate = reader.getframerate()
        raw = reader.readframes(reader.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0, rate


def _load_decoder_module(path: Path):
    spec = importlib.util.spec_from_file_location(f"decmod_{abs(hash(str(path)))}", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Module illisible : {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _build_decoder(module, encode, separator, grammar_kind: str, beam_width: int):
    from zarma_numbers.grammar import load_expression_grammar, load_grammar

    grammar = load_expression_grammar() if grammar_kind == "expressions" else load_grammar()
    lexicon = module.build_token_lexicon(grammar, encode, separator=separator)
    return module.ConstrainedCtcDecoder(
        grammar, lexicon, module.DecoderConfig(beam_width=beam_width)
    )


class Runner:
    """Charge le modèle **une fois** et exécute n'importe quelle variante dessus."""

    def __init__(self, grammar_kind: str, beam_width: int) -> None:
        from app.decoding import DecoderConfig
        from local_server import LocalAsr

        self._asr = LocalAsr(
            grammar_kind=grammar_kind, device="cpu", config=DecoderConfig(beam_width=beam_width)
        )
        encoder = self._asr._pipeline.tokenizer.create_encoder()  # noqa: SLF001

        def encode(text: str) -> list[int]:
            ids = encoder(text)
            ids = ids.tolist() if hasattr(ids, "tolist") else list(ids)
            return [int(i) for i in ids if int(i) > 3]

        self._encode = encode
        self._separator = self._asr._detect_separator(encode)  # noqa: SLF001
        self._grammar_kind = grammar_kind
        self._beam_width = beam_width
        self._decoders: dict[str, object] = {"": self._asr._decoder}  # noqa: SLF001

    def decoder_for(self, module_path: Path | None):
        key = "" if module_path is None else str(module_path)
        if key not in self._decoders:
            module = _load_decoder_module(module_path)
            self._decoders[key] = _build_decoder(
                module, self._encode, self._separator, self._grammar_kind, self._beam_width
            )
        return self._decoders[key]

    def run(self, variant: Variant, samples: np.ndarray, rate: int) -> dict[str, object]:
        import torch
        from app.vad import analyse

        torch.set_num_threads(variant.threads)
        decoder = self.decoder_for(variant.decoder_module)

        started = time.perf_counter()
        audio_s = len(samples) / rate
        kept = samples
        vad_ms = 0.0
        silent = False
        if variant.use_vad:
            mark = time.perf_counter()
            trimmed = analyse(samples, rate)
            vad_ms = (time.perf_counter() - mark) * 1000
            silent = trimmed.is_silent
            kept = trimmed.samples

        if silent:
            total_ms = (time.perf_counter() - started) * 1000
            return {
                "audio_s": audio_s,
                "kept_s": audio_s,
                "vad_ms": vad_ms,
                "model_ms": 0.0,
                "decode_ms": 0.0,
                "total_ms": total_ms,
                "text": "",
                "confidence": 0.0,
                "frames": 0,
            }

        mark = time.perf_counter()
        logits = self._asr._logits(kept, rate)  # noqa: SLF001
        model_ms = (time.perf_counter() - mark) * 1000

        mark = time.perf_counter()
        result = decoder.decode(logits)
        decode_ms = (time.perf_counter() - mark) * 1000

        total_ms = (time.perf_counter() - started) * 1000
        best = result.best
        return {
            "audio_s": audio_s,
            "kept_s": len(kept) / rate,
            "vad_ms": vad_ms,
            "model_ms": model_ms,
            "decode_ms": decode_ms,
            "total_ms": total_ms,
            "text": best.text if best and not result.rejected else "",
            "confidence": result.confidence,
            "frames": logits.shape[0],
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-decoder", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--beam-width", type=int, default=64)
    parser.add_argument("--grammar", default="expressions")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    variants = [
        Variant("reference", threads=4, use_vad=False, decoder_module=args.reference_decoder),
        Variant("optimise", threads=2, use_vad=True, decoder_module=None),
        Variant("opt_4fils", threads=4, use_vad=True, decoder_module=None),
    ]

    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    audio = {e["name"]: _read_wav(CORPUS / e["file"]) for e in manifest}
    runner = Runner(args.grammar, args.beam_width)

    # name -> variante -> liste de mesures
    results: dict[str, dict[str, list[dict]]] = {
        e["name"]: {v.name: [] for v in variants} for e in manifest
    }
    for repeat in range(args.repeats):
        for entry in manifest:
            samples, rate = audio[entry["name"]]
            for variant in variants:
                results[entry["name"]][variant.name].append(runner.run(variant, samples, rate))
        print(f"  passe {repeat + 1}/{args.repeats} terminée", flush=True)

    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    report: dict[str, object] = {"peak_rss_mb": round(peak_rss, 1), "utterances": {}}

    def median_of(runs: list[dict], key: str) -> float:
        return statistics.median(r[key] for r in runs)

    print("\n" + "=" * 118)
    print("TABLEAU AVANT / APRÈS — médianes par énoncé (ms)")
    print("=" * 118)
    print(
        f"{'énoncé':15s}{'audio':>6}{'gardé':>6} │"
        f"{'réf mod':>8}{'réf déc':>8}{'réf tot':>8} │"
        f"{'opt mod':>8}{'opt déc':>8}{'opt tot':>8} │{'gain':>7}  texte identique ?"
    )
    for entry in manifest:
        name = entry["name"]
        per = results[name]
        ref, opt = per["reference"], per["optimise"]
        ref_tot, opt_tot = median_of(ref, "total_ms"), median_of(opt, "total_ms")
        same = {r["text"] for r in ref} == {r["text"] for r in opt}
        report["utterances"][name] = {
            "condition": entry["condition"],
            "expected_text": entry["expected_text"],
            "audio_s": round(ref[0]["audio_s"], 2),
            "kept_s": round(opt[0]["kept_s"], 2),
            "variants": {
                v.name: {
                    "model_ms": round(median_of(per[v.name], "model_ms"), 1),
                    "decode_ms": round(median_of(per[v.name], "decode_ms"), 1),
                    "total_ms": round(median_of(per[v.name], "total_ms"), 1),
                    "text": per[v.name][0]["text"],
                    "confidence": round(per[v.name][0]["confidence"], 3),
                    "frames": per[v.name][0]["frames"],
                }
                for v in variants
            },
            "text_identique": same,
        }
        print(
            f"{name:15s}{ref[0]['audio_s']:6.2f}{opt[0]['kept_s']:6.2f} │"
            f"{median_of(ref, 'model_ms'):8.0f}{median_of(ref, 'decode_ms'):8.0f}{ref_tot:8.0f} │"
            f"{median_of(opt, 'model_ms'):8.0f}{median_of(opt, 'decode_ms'):8.0f}{opt_tot:8.0f} │"
            f"{ref_tot / max(opt_tot, 1e-9):6.2f}x  {'oui' if same else 'NON'}"
        )

    print("\n" + "=" * 78)
    print("AGRÉGATS (tous énoncés, toutes passes)")
    print("=" * 78)
    print(f"{'variante':14s}{'p50':>9}{'p95':>9}{'max':>9}{'moy modèle':>12}{'moy décod':>11}")
    report["aggregate"] = {}
    for variant in variants:
        totals = [r["total_ms"] for name in results for r in results[name][variant.name]]
        models = [r["model_ms"] for name in results for r in results[name][variant.name]]
        decodes = [r["decode_ms"] for name in results for r in results[name][variant.name]]
        agg = {
            "p50_ms": round(_percentile(totals, 50), 1),
            "p95_ms": round(_percentile(totals, 95), 1),
            "max_ms": round(max(totals), 1),
            "mean_model_ms": round(statistics.mean(models), 1),
            "mean_decode_ms": round(statistics.mean(decodes), 1),
        }
        report["aggregate"][variant.name] = agg
        print(
            f"{variant.name:14s}{agg['p50_ms']:9.0f}{agg['p95_ms']:9.0f}{agg['max_ms']:9.0f}"
            f"{agg['mean_model_ms']:12.0f}{agg['mean_decode_ms']:11.0f}"
        )

    # Les énoncés de 5 à 8 s sont la cible annoncée (p50 ≤ 3 s, p95 ≤ 5 s) :
    # les agréger séparément évite que les énoncés courts flattent le résultat.
    print(f"\nCIBLE — énoncés de 5 à 8 s seulement ({'p50 ≤ 3000 ms, p95 ≤ 5000 ms'})")
    report["cible_5_8s"] = {}
    for variant in variants:
        totals = [
            r["total_ms"]
            for name in results
            for r in results[name][variant.name]
            if 5.0 <= r["audio_s"] <= 8.5
        ]
        agg = {
            "p50_ms": round(_percentile(totals, 50), 1),
            "p95_ms": round(_percentile(totals, 95), 1),
        }
        report["cible_5_8s"][variant.name] = agg
        verdict = "✅" if agg["p50_ms"] <= 3000 and agg["p95_ms"] <= 5000 else "❌"
        print(
            f"  {variant.name:14s} p50 {agg['p50_ms']:7.0f} ms · "
            f"p95 {agg['p95_ms']:7.0f} ms  {verdict}"
        )

    print(f"\nRSS maximal du processus : {peak_rss:.0f} Mo")
    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"rapport → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
