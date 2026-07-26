#!/usr/bin/env python
"""Compare le décodeur **de référence** et le décodeur courant sur logits réels.

Toute la valeur de ce script tient dans une propriété : il n'a besoin **ni du
modèle, ni de GPU, ni du tokenizer**. Il reconstruit l'automate exact à partir du
lexique exporté (``inference_experiments.py --dump-lexicon``) et rejoue les
logits capturés en ``.npy``. Une modification du décodeur se valide donc en
quelques secondes, en CI comme sur le VPS, sans les 2 Go du modèle.

Le critère est volontairement dur : **égalité bit à bit** des scores, pas une
tolérance. Une optimisation du décodeur qui change la 12ᵉ décimale d'une NLL
peut, sur une hypothèse serrée, inverser deux candidats et donc changer une
décision ``accept``/``confirm``. Tant qu'on peut exiger l'exactitude, l'exiger
coûte moins cher que de devoir prouver après coup qu'un écart est bénin.

Usage :
    asrenv/bin/python scripts/bench/decoder_equivalence.py \
        --lexicon lexicon.json --logits out/ --reference ref/decoding.py
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path
from types import ModuleType

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services" / "asr"))


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Module illisible : {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _build_decoder(module: ModuleType, lexicon_data: dict, grammar_kind: str, beam_width: int):
    """Reconstruit décodeur + automate depuis le lexique exporté."""
    from zarma_numbers.grammar import load_expression_grammar, load_grammar

    grammar = load_expression_grammar() if grammar_kind == "expressions" else load_grammar()
    entries = {
        word: tuple(tuple(int(i) for i in ids) for ids in spellings)
        for word, spellings in lexicon_data[grammar_kind].items()
    }
    lexicon = module.TokenLexicon(
        entries=entries, separator=tuple(int(i) for i in lexicon_data["separator"])
    )
    config = module.DecoderConfig(beam_width=beam_width)
    return module.ConstrainedCtcDecoder(grammar, lexicon, config)


def _summary(result) -> dict[str, object]:
    """Extrait tout ce qui doit rester identique — scores compris, en exact."""
    return {
        "frame_count": result.frame_count,
        "free_path_nll": repr(result.free_path_nll),
        "reject_threshold": repr(result.reject_threshold),
        "rejected": result.rejected,
        "confidence": repr(result.confidence),
        "hypotheses": [
            {
                "text": h.text,
                "token_ids": list(h.token_ids),
                "nll": repr(h.neg_log_likelihood),
                "score": repr(h.score),
                "confidence": repr(h.confidence),
            }
            for h in result.hypotheses
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lexicon", type=Path, required=True)
    parser.add_argument("--logits", type=Path, required=True)
    parser.add_argument(
        "--reference", type=Path, default=None, help="decoding.py de référence (avant optimisation)"
    )
    parser.add_argument("--grammar", default="expressions")
    parser.add_argument("--beam-width", type=int, default=64)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--only", default=None)
    args = parser.parse_args(argv)

    lexicon_data = json.loads(args.lexicon.read_text(encoding="utf-8"))
    files = sorted(args.logits.glob("*.npy"))
    if args.only:
        files = [f for f in files if args.only in f.stem]
    if not files:
        raise SystemExit(f"Aucun .npy dans {args.logits}")

    current = _load_module(REPO / "services" / "asr" / "app" / "decoding.py", "decoding_current")
    cur_dec = _build_decoder(current, lexicon_data, args.grammar, args.beam_width)

    ref_dec = None
    if args.reference:
        reference = _load_module(args.reference, "decoding_reference")
        ref_dec = _build_decoder(reference, lexicon_data, args.grammar, args.beam_width)

    print(f"{'énoncé':16s}{'T':>5}{'réf ms':>9}{'opt ms':>9}{'gain':>8}  verdict")
    mismatches: list[str] = []
    ref_total = cur_total = 0.0
    for path in files:
        logits = np.load(path)
        cur_times = []
        for _ in range(args.repeats):
            mark = time.perf_counter()
            cur_result = cur_dec.decode(logits)
            cur_times.append((time.perf_counter() - mark) * 1000)
        cur_ms = statistics.median(cur_times)
        cur_total += cur_ms

        ref_ms = float("nan")
        verdict = "—"
        if ref_dec is not None:
            ref_times = []
            for _ in range(args.repeats):
                mark = time.perf_counter()
                ref_result = ref_dec.decode(logits)
                ref_times.append((time.perf_counter() - mark) * 1000)
            ref_ms = statistics.median(ref_times)
            ref_total += ref_ms
            same = _summary(ref_result) == _summary(cur_result)
            verdict = "IDENTIQUE" if same else "DIVERGE"
            if not same:
                mismatches.append(path.stem)
        speed = f"x{ref_ms / cur_ms:.1f}" if ref_dec is not None and cur_ms > 0 else "—"
        print(
            f"{path.stem:16s}{logits.shape[0]:5d}{ref_ms:9.1f}{cur_ms:9.1f}{speed:>8}  {verdict}",
            flush=True,
        )

    if ref_dec is not None:
        print(
            f"\ntotal : référence {ref_total:.0f} ms → optimisé {cur_total:.0f} ms "
            f"(x{ref_total / cur_total:.1f})"
        )
        if mismatches:
            print(f"\n❌ DIVERGENCES sur : {', '.join(mismatches)}")
            # Détail de la première divergence, pour rendre l'échec actionnable.
            logits = np.load(args.logits / f"{mismatches[0]}.npy")
            a, b = _summary(ref_dec.decode(logits)), _summary(cur_dec.decode(logits))
            for key in a:
                if a[key] != b[key]:
                    print(f"  champ « {key} » :\n    réf = {a[key]}\n    opt = {b[key]}")
            return 1
        print("✅ Sorties identiques bit à bit sur tous les énoncés.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
