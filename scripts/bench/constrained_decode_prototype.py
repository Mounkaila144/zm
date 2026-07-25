#!/usr/bin/env python
"""PROTOTYPE — décodage CTC **contraint** à la grammaire des nombres zarma.

⚠️ Prototype de recherche, **pas** du code de production. Il démontre
empiriquement que le problème du modèle CTC d'Omnilingual n'est pas le modèle
mais le **décodage glouton** : les logits contiennent l'information latine
correcte, écrasée par l'``argmax`` trame par trame.

Principe
--------
1. On capture les **logits** du modèle CTC (le pipeline officiel les calcule
   puis les jette : ``logits, _ = self.model(...)`` puis ``torch.argmax(...)``).
2. Pour chaque nombre candidat, on encode sa **forme canonique** (source unique :
   ``zarma_numbers.generate``) et on calcule ``-log P(candidat | logits)`` avec
   l'algorithme CTC (``torch.nn.functional.ctc_loss``).
3. On retient le candidat de meilleur score, **normalisé par la longueur** —
   sans cette normalisation, le biais de longueur du CTC favorise
   systématiquement les formes courtes (``afo``).

Ce n'est **pas** du fuzzy matching : aucune distance d'édition textuelle n'est
utilisée. C'est une recherche acoustique restreinte à un espace de sorties
valides par construction — toute sortie est parseable par le moteur déterministe.

Résultat mesuré (1 locuteur, 18 fichiers, nombres 0–20, condition calme)
-----------------------------------------------------------------------
- décodage glouton (pipeline officiel) ........ 1/18
- contraint, score brut ....................... 10/18
- contraint + normalisation par longueur ...... **18/18**

Limites connues (À NE PAS OUBLIER)
----------------------------------
- Ici le choix se fait parmi **21 candidats énumérés** (0–20). En production
  l'espace est 0–1 000 000 : il faudra une **recherche en faisceau sur un
  automate/trie** de la grammaire (cf. ``pyctcdecode`` / décodeur flashlight),
  pas une énumération.
- **Aucun mécanisme de rejet** : le décodeur choisit toujours un candidat. Un
  bruit ou une toux produirait un nombre valide. Il FAUT comparer le score
  contraint au score libre (ou une probabilité normalisée) et **rejeter**
  au-delà d'un seuil → ``decision = repeat`` (FR21/NFR14).
- Mesuré sur **1 locuteur**, en condition calme uniquement.

Exécution (dans l'environnement ASR isolé, cf. README-local-asr.md)
-------------------------------------------------------------------
    export DYLD_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_LIBRARY_PATH
    asrenv/bin/python scripts/bench/constrained_decode_prototype.py \
        --audio-dir ~/Music/v1 --candidates /tmp/cands.json

``--candidates`` est un JSON ``{"<nombre>": "<forme canonique>"}`` produit côté
projet par ``zarma_numbers.generate`` (le paquet cœur n'est pas installé dans
l'environnement ASR).
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from pathlib import Path

import torch
import torch.nn.functional as F
from omnilingual_asr.models.inference import pipeline as P

CTC_MODEL = "omniASR_CTC_300M_v2"
#: Poids du pénalisateur de longueur ; None = normalisation par longueur.
_captured: dict = {}


def _install_logit_probe() -> None:
    """Intercepte le forward CTC pour capturer les logits avant l'``argmax``."""

    original = P.ASRInferencePipeline._apply_model_wav2vec2asr

    def patched(self, batch):
        layout = P.BatchLayout(
            batch.source_seqs.shape,
            seq_lens=batch.source_seq_lens,
            device=batch.source_seqs.device,
        )
        logits, out_layout = self.model(batch.source_seqs, layout)
        _captured["logits"] = logits.detach().float().cpu()
        _captured["lens"] = list(out_layout.seq_lens)
        return original(self, batch)

    P.ASRInferencePipeline._apply_model_wav2vec2asr = patched


def _token_ids(encoder, text: str) -> list[int]:
    """Encode une forme canonique en ids, sans les tokens spéciaux bas."""

    tokens = encoder(text)
    tokens = tokens.tolist() if hasattr(tokens, "tolist") else list(tokens)
    return [token for token in tokens if token > 3]


def ctc_score(log_probs: torch.Tensor, ids: list[int], blank: int = 0) -> float:
    """``-log P(ids | logits)`` ; plus bas = plus probable."""

    if not ids:
        return float("inf")
    frames = log_probs.shape[0]
    return F.ctc_loss(
        log_probs.unsqueeze(1),
        torch.tensor([ids]),
        torch.tensor([frames]),
        torch.tensor([len(ids)]),
        blank=blank,
        reduction="sum",
        zero_infinity=True,
    ).item()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prototype de décodage CTC contraint.")
    parser.add_argument("--audio-dir", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--pattern", default=r"v1-(\d+)", help="Regex extrayant la vérité terrain.")
    args = parser.parse_args(argv)

    candidates: dict[str, str] = json.loads(args.candidates.read_text(encoding="utf-8"))

    _install_logit_probe()
    pipe = P.ASRInferencePipeline(model_card=CTC_MODEL, device="cpu", dtype=torch.float32)
    encoder = pipe.tokenizer.create_encoder()
    candidate_ids = {key: _token_ids(encoder, text) for key, text in candidates.items()}

    files = sorted(
        glob.glob(str(args.audio_dir / "*.wav")),
        key=lambda f: int(re.search(args.pattern, f).group(1)),
    )

    greedy_ok = constrained_ok = 0
    print(f"{'att.':>5} | {'glouton':<20} | {'contraint':<20} | ok")
    print("-" * 62)
    for path in files:
        expected = re.search(args.pattern, path).group(1)
        greedy = pipe.transcribe([path])[0]
        logits = _captured["logits"][0][: _captured["lens"][0]]
        log_probs = F.log_softmax(logits, dim=-1)

        # Normalisation par longueur : neutralise le biais du CTC vers les
        # séquences courtes (sans elle, tout converge vers « afo »).
        best = min(
            candidate_ids,
            key=lambda key: (
                ctc_score(log_probs, candidate_ids[key]) / max(1, len(candidate_ids[key]))
            ),
        )
        greedy_ok += greedy.strip() == candidates.get(expected, "")
        constrained_ok += best == expected
        shown = greedy if greedy.isascii() else "(script non-latin)"
        print(
            f"{expected:>5} | {shown:<20.20} | {best:>3} = {candidates[best]:<14.14} | "
            f"{'OK' if best == expected else ''}"
        )
    print("-" * 62)
    total = len(files)
    print(f"glouton   : {greedy_ok}/{total}")
    print(f"contraint : {constrained_ok}/{total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
