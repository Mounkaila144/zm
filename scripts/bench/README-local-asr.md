# ASR local (benchmark sans cloud) — Omnilingual sur Apple Silicon

Permet de faire tourner les modèles **Omnilingual ASR** (CTC/LLM) **localement**
(ex. MacBook M1) pour produire les hypothèses du benchmark 5.4, puis recalculer
les métriques via le harnais 5.2 en **mode rejeu**. Modal (story 5.3) reste réservé
à la **production** ; le benchmark, lui, peut être 100 % local.

> Environnement **isolé** du projet API : les dépendances lourdes (torch,
> fairseq2, omnilingual-asr) ne sont **jamais** ajoutées au workspace uv racine
> (la CI reste sans GPU).

## 1. Prérequis système (macOS)

```bash
brew install libsndfile          # requis par le binaire natif fairseq2n
```

fairseq2n cherche `libsndfile` dans les chemins système ; exposer Homebrew :

```bash
export DYLD_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_LIBRARY_PATH
```

## 2. Environnement Python isolé

```bash
uv venv --python 3.11 asrenv          # Python 3.10–3.12 requis
uv pip install --python asrenv/bin/python omnilingual-asr
```

Compatibilité validée sur M1 / macOS récent : `fairseq2n` publie des wheels
`macosx_14_0_arm64`, `torch` expose le backend **MPS** (GPU Apple).

## 3. Transcrire les audios → dump d'hypothèses

Place tes WAV (PCM16 mono 16 kHz) sous `dataset/benchmark/` selon les `audio_path`
du manifest 5.1, puis :

```bash
export DYLD_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_LIBRARY_PATH
asrenv/bin/python scripts/bench/transcribe_local.py \
    --manifest dataset/manifests/benchmark.jsonl \
    --audio-root dataset/benchmark \
    --model ctc \
    --out dataset/benchmark/hypotheses/ctc.jsonl
# idem avec --model llm --out …/llm.jsonl
```

Le dump reste **hors Git** (`dataset/benchmark/**/*.jsonl`).

## 4. Calculer les métriques (env du projet, sans GPU)

```bash
uv run python scripts/bench/run_benchmark.py \
    --manifest dataset/manifests/benchmark.jsonl \
    --hypotheses dataset/benchmark/hypotheses/ctc.jsonl \
    --split test --out docs/qa/benchmarks/benchmark-ctc-test
```

## Limite connue

L'API haut-niveau `ASRInferencePipeline.transcribe` ne renvoie que le **texte**
(pas de score acoustique ni d'alternatives). `transcribe_local.py` écrit donc un
`acoustic_score` fixe (`--acoustic-score`, défaut 1.0) et des `candidates` vides.
→ L'**Exact Number Accuracy** n'en dépend pas ; les taux accept/confirm/repeat
sont à interpréter avec cette réserve (à mentionner dans le rapport de décision).
