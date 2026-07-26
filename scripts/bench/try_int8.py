#!/usr/bin/env python
"""Quantification dynamique INT8 : gain réel et coût en reconnaissance.

Pourquoi ce n'est pas immédiat
------------------------------

96 % des paramètres du modèle (313 M sur 326 M) sont dans 146 couches linéaires.
C'est la cible naturelle de ``torch.ao.quantization.quantize_dynamic``. Mais
``fairseq2.nn.Linear`` **n'hérite pas** de ``torch.nn.Linear`` : la fonction ne
reconnaît aucune couche et ne fait rien — c'est ce qu'on observe si on l'appelle
naïvement.

Or la documentation de fairseq2 est explicite, et la lecture du code le confirme :
cette classe *est* ``torch.nn.Linear``, au type près (même ``forward``, appel à
``torch.nn.functional.linear`` sur les mêmes ``weight``/``bias``). La substitution
est donc **exacte**, et ce script la vérifie plutôt que de la supposer : les
logits produits avant et après échange doivent être identiques bit à bit. Sans
cette vérification, un écart de reconnaissance ultérieur serait impossible à
attribuer — vient-il de la substitution ou de la quantification ?

Ce que le script mesure ensuite est le seul critère qui compte :
le **texte décodé** et la **confiance**, pas une norme d'écart sur les logits.
Un modèle acoustique peut voir ses logits bouger sensiblement sans que la
meilleure hypothèse contrainte change ; l'inverse existe aussi.

Avertissement matériel : ce VPS est un AMD famille 23 (Zen/Zen+/Zen2) — AVX2
mais **ni AVX-512 ni VNNI**. Le noyau INT8 de fbgemm y tourne sans son
accélération dédiée : attendre 1,5 à 2×, pas les 3 à 4× annoncés sur un Xeon
récent.

La quantification est appliquée **en place** : conserver simultanément une copie
float32 et une copie INT8 demanderait ~4 Go dans un processus, sur une machine
qui en a 8 et fait déjà tourner l'API et le service ASR de production.
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


def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as reader:
        rate = reader.getframerate()
        raw = reader.readframes(reader.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0, rate


def swap_to_torch_linear(model) -> int:
    """Remplace chaque ``fairseq2.nn.Linear`` par un ``torch.nn.Linear`` équivalent.

    Les tenseurs de poids sont **réutilisés tels quels** (pas de copie) : l'échange
    ne coûte ni mémoire ni précision, il ne change que le type Python vu par les
    outils de quantification de PyTorch.
    """
    import torch
    from fairseq2.nn import Linear as Fairseq2Linear

    replaced = 0
    for module in model.modules():
        for name, child in list(module.named_children()):
            if not isinstance(child, Fairseq2Linear):
                continue
            replacement = torch.nn.Linear(
                child.weight.shape[1], child.weight.shape[0], bias=child.bias is not None
            )
            replacement.weight = child.weight
            if child.bias is not None:
                replacement.bias = child.bias
            setattr(module, name, replacement)
            replaced += 1
    return replaced


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--beam-width", type=int, default=64)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    import torch

    torch.set_num_threads(args.threads)

    from app.decoding import DecoderConfig
    from local_server import LocalAsr

    asr = LocalAsr(
        grammar_kind="expressions", device="cpu", config=DecoderConfig(beam_width=args.beam_width)
    )
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    audio = {e["name"]: _read_wav(CORPUS / e["file"]) for e in manifest}

    def run_all() -> tuple[dict[str, float], dict[str, np.ndarray]]:
        times: dict[str, list[float]] = {}
        logits: dict[str, np.ndarray] = {}
        for _ in range(args.repeats):
            for entry in manifest:
                samples, rate = audio[entry["name"]]
                mark = time.perf_counter()
                out = asr._logits(samples, rate)  # noqa: SLF001
                times.setdefault(entry["name"], []).append((time.perf_counter() - mark) * 1000)
                logits[entry["name"]] = out
        return {k: statistics.median(v) for k, v in times.items()}, logits

    # 1) Référence float32, avant toute manipulation.
    print("mesure float32 (référence)…", flush=True)
    fp32_ms, fp32_logits = run_all()

    # 2) Échange de type — doit être rigoureusement neutre.
    replaced = swap_to_torch_linear(asr._pipeline.model)  # noqa: SLF001
    print(f"{replaced} couches fairseq2.nn.Linear → torch.nn.Linear", flush=True)
    check_name = manifest[len(manifest) // 2]["name"]
    samples, rate = audio[check_name]
    after_swap = asr._logits(samples, rate)  # noqa: SLF001
    identical = np.array_equal(after_swap, fp32_logits[check_name])
    print(f"logits identiques bit à bit après échange : {identical}")
    if not identical:
        largest = float(np.abs(after_swap - fp32_logits[check_name]).max())
        print(f"  ⛔ écart maximal {largest:.3e} — la substitution n'est pas neutre, on s'arrête.")
        return 1

    # 3) Quantification en place.
    print("quantification INT8 (en place)…", flush=True)
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    torch.ao.quantization.quantize_dynamic(
        asr._pipeline.model,  # noqa: SLF001
        {torch.nn.Linear},
        dtype=torch.qint8,
        inplace=True,
    )
    quantized = sum(
        1
        for m in asr._pipeline.model.modules()  # noqa: SLF001
        if type(m).__name__ == "Linear" and "quantized" in type(m).__module__
    )
    print(f"{quantized} couches quantifiées", flush=True)
    if quantized == 0:
        print("  ⛔ aucune couche quantifiée — chemin inopérant.")
        return 1

    print("mesure INT8…", flush=True)
    int8_ms, int8_logits = run_all()
    rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0

    rows = []
    print(
        f"\n{'énoncé':15s}{'fp32 ms':>9}{'int8 ms':>9}{'gain':>7}{'MAE':>9}"
        f"{'conf fp32':>11}{'conf int8':>11}  texte"
    )
    identical_count = 0
    for entry in manifest:
        name = entry["name"]
        a, b = fp32_logits[name], int8_logits[name]
        ra = asr._decoder.decode(a)  # noqa: SLF001
        rb = asr._decoder.decode(b)  # noqa: SLF001
        text_a = "" if ra.rejected else ra.best.text
        text_b = "" if rb.rejected else rb.best.text
        same = text_a == text_b
        identical_count += same
        mae = float(np.abs(a - b).mean()) if a.shape == b.shape else float("nan")
        rows.append(
            {
                "name": name,
                "condition": entry["condition"],
                "expected_text": entry["expected_text"],
                "fp32_ms": round(fp32_ms[name], 1),
                "int8_ms": round(int8_ms[name], 1),
                "logits_mae": round(mae, 4),
                "text_fp32": text_a,
                "text_int8": text_b,
                "conf_fp32": round(ra.confidence, 3),
                "conf_int8": round(rb.confidence, 3),
                "identique": same,
            }
        )
        print(
            f"{name:15s}{fp32_ms[name]:9.0f}{int8_ms[name]:9.0f}"
            f"{fp32_ms[name] / max(int8_ms[name], 1e-9):6.2f}x{mae:9.3f}"
            f"{ra.confidence:11.3f}{rb.confidence:11.3f}  {'=' if same else 'DIFFÉRENT'}"
        )
        if not same:
            print(f"    fp32 « {text_a} »")
            print(f"    int8 « {text_b} »")

    total_fp32 = sum(fp32_ms.values())
    total_int8 = sum(int8_ms.values())
    print(
        f"\nglobal : {total_fp32:.0f} ms → {total_int8:.0f} ms "
        f"(x{total_fp32 / total_int8:.2f}) · textes identiques : "
        f"{identical_count}/{len(manifest)}"
    )
    print(f"RSS : {rss_before:.0f} Mo avant quantification → {rss_after:.0f} Mo après")

    if args.out:
        args.out.write_text(
            json.dumps(
                {
                    "threads": args.threads,
                    "couches_quantifiees": quantized,
                    "total_fp32_ms": round(total_fp32, 1),
                    "total_int8_ms": round(total_int8, 1),
                    "textes_identiques": identical_count,
                    "total_enonces": len(manifest),
                    "rss_avant_mb": round(rss_before, 1),
                    "rss_apres_mb": round(rss_after, 1),
                    "resultats": rows,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"rapport → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
