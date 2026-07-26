#!/usr/bin/env python
"""Expériences sur le **chemin d'inférence** — un seul chargement de modèle.

Le profilage de référence a montré que l'inférence PyTorch pèse ~88 % du temps
de calcul. Trois questions décident de ce qu'on peut en retirer, et chacune
demande le vrai modèle :

1. **Combien de threads ?** Le service est réglé sur 4. Les mesures GEMM
   suggèrent que le passage de 2 à 4 threads n'apporte rien, voire régresse —
   cohérent avec les 237 % de CPU observés (59 % d'efficacité parallèle). À
   vérifier de bout en bout, pas sur une matrice isolée.

2. **La quantification dynamique INT8 tient-elle ?** Ce CPU (Zen, famille 23)
   n'a ni AVX-512 ni VNNI : le gain sera plus modeste que sur un Xeon récent.
   Reste à savoir s'il existe, et surtout **ce qu'il coûte en précision** — ce
   qui se juge sur le texte décodé, pas sur une norme de logits.

3. **Quelle est la structure de la variance ?** Le même énoncé rejoué plusieurs
   fois donne 8,5 à 24,6 ms/trame. Tant que cette dispersion n'est pas comprise,
   viser un p95 est illusoire.

Le script exporte aussi le **lexique tokenizer** (``--dump-lexicon``) : c'est ce
qui permet de reconstruire l'automate exact hors ligne et de valider toute
modification du décodeur sans jamais recharger le modèle.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services" / "asr"))
CORPUS = REPO / "dataset" / "benchmark" / "perf"


def _load(grammar_kind: str, beam_width: int):
    from app.decoding import DecoderConfig
    from local_server import LocalAsr

    return LocalAsr(
        grammar_kind=grammar_kind, device="cpu", config=DecoderConfig(beam_width=beam_width)
    )


def _infer_only(asr, samples: np.ndarray, sample_rate: int) -> tuple[float, np.ndarray]:
    """Chronomètre le seul passage avant du modèle (hors préparation du lot)."""
    import torch
    from fairseq2.data.data_pipeline import DataPipeline, read_sequence
    from fairseq2.nn.batch_layout import BatchLayout

    builder = DataPipeline.zip(
        [
            asr._pipeline._build_audio_wavform_pipeline(  # noqa: SLF001
                [{"waveform": samples, "sample_rate": sample_rate}]
            ).and_return(),
            read_sequence([None]).and_return(),
        ]
    )
    batch = next(
        iter(builder.bucket(1).map(asr._pipeline._create_batch_simple).and_return())
    )  # noqa: SLF001
    seqs = batch.source_seqs.to(device=asr._device, dtype=asr._dtype)  # noqa: SLF001
    layout = BatchLayout(seqs.shape, seq_lens=batch.source_seq_lens, device=seqs.device)
    mark = time.perf_counter()
    with torch.inference_mode():
        logits, out_layout = asr._pipeline.model(seqs, layout)  # noqa: SLF001
    elapsed = time.perf_counter() - mark
    length = int(list(out_layout.seq_lens)[0])
    return elapsed, logits[0, :length].detach().float().cpu().numpy()


def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    import wave

    with wave.open(str(path), "rb") as reader:
        rate = reader.getframerate()
        raw = reader.readframes(reader.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0, rate


def dump_lexicon(asr, out: Path) -> None:
    """Exporte grammaire + encodages tokenizer : l'automate devient reconstructible.

    Sans cet export, toute vérification du décodeur exige les 2 Go du modèle,
    donc ~15 s de chargement et une pression mémoire réelle sur un VPS à 8 Go.
    Avec, la suite de non-régression tourne en quelques secondes en CI.
    """
    from zarma_numbers.grammar import load_expression_grammar, load_grammar

    encoder = asr._pipeline.tokenizer.create_encoder()  # noqa: SLF001

    def encode(text: str) -> list[int]:
        ids = encoder(text)
        ids = ids.tolist() if hasattr(ids, "tolist") else list(ids)
        return [int(i) for i in ids if int(i) > 3]

    payload: dict[str, object] = {"separator": list(asr._detect_separator(encode))}  # noqa: SLF001
    for kind, loader in (("expressions", load_expression_grammar), ("numbers", load_grammar)):
        grammar = loader()
        payload[kind] = {
            word: [encode(spelling) for spelling in grammar.pronunciations[word]]
            for word in sorted(grammar.tokens)
        }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"lexique → {out}")


def sweep_threads(asr, names: list[str], repeats: int) -> dict[int, dict[str, float]]:
    """Balaye le nombre de threads torch, en **entrelaçant** les configurations.

    Entrelacer est indispensable : mesurer 1 thread pendant dix minutes puis
    4 threads pendant dix minutes attribuerait à la configuration toute dérive de
    charge de la machine survenue entre les deux. En alternant, une perturbation
    ponctuelle frappe les deux également.
    """
    import torch

    audio = {n: _read_wav(CORPUS / f"{n}.wav") for n in names}
    samples: dict[int, dict[str, list[float]]] = {t: {n: [] for n in names} for t in (1, 2, 3, 4)}
    for _ in range(repeats):
        for threads in (1, 2, 3, 4):
            torch.set_num_threads(threads)
            for name in names:
                wav, rate = audio[name]
                elapsed, _ = _infer_only(asr, wav, rate)
                samples[threads][name].append(elapsed * 1000.0)
    return {
        t: {n: statistics.median(v) for n, v in per_name.items()} for t, per_name in samples.items()
    }


def try_int8(asr, names: list[str], repeats: int) -> dict[str, object]:
    """Quantification dynamique INT8 des couches linéaires : gain **et** fidélité.

    On compare les logits float32 et INT8 sur les mêmes entrées, puis on décode
    les deux. Le critère qui compte est le **texte décodé**, pas un écart de
    norme : un modèle acoustique peut voir ses logits bouger sensiblement sans
    que la meilleure hypothèse contrainte change, et l'inverse est vrai aussi.
    """
    import copy

    import torch

    linear_count = sum(
        1 for m in asr._pipeline.model.modules() if isinstance(m, torch.nn.Linear)
    )  # noqa: SLF001
    if linear_count == 0:
        return {"supporte": False, "raison": "aucun torch.nn.Linear détecté"}

    torch.set_num_threads(2)
    audio = {n: _read_wav(CORPUS / f"{n}.wav") for n in names}
    base_ms: dict[str, list[float]] = {n: [] for n in names}
    base_logits: dict[str, np.ndarray] = {}
    for _ in range(repeats):
        for name in names:
            wav, rate = audio[name]
            elapsed, logits = _infer_only(asr, wav, rate)
            base_ms[name].append(elapsed * 1000.0)
            base_logits[name] = logits

    original = asr._pipeline.model  # noqa: SLF001
    quantized = torch.ao.quantization.quantize_dynamic(
        copy.deepcopy(original).eval(), {torch.nn.Linear}, dtype=torch.qint8
    )
    asr._pipeline.model = quantized  # noqa: SLF001
    q_ms: dict[str, list[float]] = {n: [] for n in names}
    q_logits: dict[str, np.ndarray] = {}
    try:
        for _ in range(repeats):
            for name in names:
                wav, rate = audio[name]
                elapsed, logits = _infer_only(asr, wav, rate)
                q_ms[name].append(elapsed * 1000.0)
                q_logits[name] = logits
    finally:
        asr._pipeline.model = original  # noqa: SLF001

    rows = []
    for name in names:
        a, b = base_logits[name], q_logits[name]
        texte_fp32 = asr._decoder.decode(a).best  # noqa: SLF001
        texte_int8 = asr._decoder.decode(b).best  # noqa: SLF001
        rows.append(
            {
                "name": name,
                "fp32_ms": round(statistics.median(base_ms[name]), 1),
                "int8_ms": round(statistics.median(q_ms[name]), 1),
                "logits_mae": round(float(np.abs(a - b).mean()), 4) if a.shape == b.shape else None,
                "texte_fp32": texte_fp32.text if texte_fp32 else "",
                "texte_int8": texte_int8.text if texte_int8 else "",
                "conf_fp32": round(texte_fp32.confidence, 3) if texte_fp32 else 0.0,
                "conf_int8": round(texte_int8.confidence, 3) if texte_int8 else 0.0,
            }
        )
    return {"supporte": True, "couches_lineaires": linear_count, "resultats": rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--beam-width", type=int, default=64)
    parser.add_argument("--grammar", default="expressions")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--dump-lexicon", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--names", default="court_2,moyen_3,long_2", help="énoncés utilisés pour les sweeps"
    )
    parser.add_argument("--skip-int8", action="store_true")
    args = parser.parse_args(argv)

    names = [n.strip() for n in args.names.split(",") if n.strip()]
    asr = _load(args.grammar, args.beam_width)
    if args.dump_lexicon:
        dump_lexicon(asr, args.dump_lexicon)

    report: dict[str, object] = {}

    print("\n=== Balayage du nombre de threads (ms d'inférence, médiane) ===")
    sweep = sweep_threads(asr, names, args.repeats)
    header = "  " + "énoncé".ljust(14) + "".join(f"{t} thread".rjust(11) for t in (1, 2, 3, 4))
    print(header)
    for name in names:
        row = "  " + name.ljust(14)
        for t in (1, 2, 3, 4):
            row += f"{sweep[t][name]:11.0f}"
        best = min((sweep[t][name], t) for t in (1, 2, 3, 4))
        row += f"   → meilleur : {best[1]} thread(s)"
        print(row)
    report["sweep_threads"] = {str(t): sweep[t] for t in sweep}

    if not args.skip_int8:
        print("\n=== Quantification dynamique INT8 ===")
        int8 = try_int8(asr, names, args.repeats)
        report["int8"] = int8
        if int8.get("supporte"):
            print(f"  {int8['couches_lineaires']} couches nn.Linear quantifiées")
            for row in int8["resultats"]:
                verdict = "IDENTIQUE" if row["texte_fp32"] == row["texte_int8"] else "DIVERGE"
                print(
                    f"  {row['name']:14s} fp32 {row['fp32_ms']:7.0f} ms "
                    f"→ int8 {row['int8_ms']:7.0f} ms "
                    f"(x{row['fp32_ms'] / max(row['int8_ms'], 1e-9):.2f}) · "
                    f"MAE {row['logits_mae']} · {verdict}"
                )
                if verdict == "DIVERGE":
                    print(f"      fp32 « {row['texte_fp32']} »")
                    print(f"      int8 « {row['texte_int8']} »")
        else:
            print(f"  non applicable : {int8.get('raison')}")

    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nrapport → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
