# scripts

Scripts transverses : bootstrap, seed, bench, deploy.

## Revue et intégration des contributions au dataset (story 4.5)

Outils **locaux** réservés au responsable données. Aucun back-office web ni
authentification admin : la sécurité repose sur les permissions du poste. Un
retrait (`withdrawn`) est terminal — aucune commande ne peut le restaurer.

### Configuration

Toute la config passe par `Settings` (variables d'environnement / `.env`) :

- `DATABASE_URL` — base des métadonnées (SQLite en dev, PostgreSQL en prod).
- `AUDIO_STORAGE_DIR` — racine du stockage audio consenti (hors base, hors Git).

### Cycle `list → review → validate/reject → build-manifest`

```bash
# 1) Lister les contributions en attente (projection sûre : ni anon_id,
#    ni device_info, ni chemin absolu). La colonne `réf=` est le nom de fichier
#    opaque relatif à AUDIO_STORAGE_DIR.
uv run python scripts/review_contributions.py list --limit 50 --offset 0

# 2) Écouter l'audio localement depuis la racine configurée :
#    <AUDIO_STORAGE_DIR>/<réf>   (ex. lecteur audio du poste opérateur)

# 3) Décider explicitement, par UUID (confirmation interactive sauf --yes) :
uv run python scripts/review_contributions.py validate <UUID>
uv run python scripts/review_contributions.py reject   <UUID> --yes

# 4) Générer le manifest dataset (split par locuteur, fail-closed) :
uv run python scripts/build_dataset_manifest.py \
    --output dataset/manifests/manifest.jsonl
```

### Règles de confidentialité

- Aucune sortie opérateur ni log ne contient `anon_id`, `device_info` ou de
  chemin absolu ; seules la référence audio opaque et la région coarse sont
  affichées.
- Les décisions sont idempotentes : réappliquer la même décision est un no-op
  signalé.
- `build_dataset_manifest.py` est **fail-closed** : la moindre entrée invalide
  (audio absent, illisible, non canonique, métadonnée manquante) empêche toute
  écriture. `--allow-partial` exclut explicitement les invalides et publie le
  reste. L'écriture est atomique (fichier temporaire puis renommage).

Voir `dataset/README.md` pour le schéma du manifest, la seed de split et la
procédure de reconstruction.

## Corpus de benchmark (story 5.1)

Outils **sans GPU** de constitution d'un corpus d'évaluation reproductible avec
**split strict par locuteur** (anti-fuite, NFR10). Les cibles et les paires de
confusion sont dérivées du moteur `zarma_numbers` (source unique).

```bash
# 1) Plan d'enregistrement (quoi enregistrer, ≥ 100 audios, courts/longs/confusion) :
uv run python scripts/bench/build_benchmark_corpus.py plan \
    --speakers spk01 spk02 spk03 spk04 \
    --out dataset/benchmark/recording_plan.jsonl

# 2) Assembler le manifest versionné depuis l'index des audios enregistrés :
uv run python scripts/bench/build_benchmark_corpus.py build \
    --source dataset/benchmark/source_index.jsonl \
    --benchmark-dir dataset/benchmark \
    --out dataset/manifests/benchmark.jsonl

# 3) Valider l'intégrité (vérité terrain, non-fuite de locuteur, couverture) :
uv run python scripts/bench/build_benchmark_corpus.py validate \
    --manifest dataset/manifests/benchmark.jsonl
```

- **Split par locuteur** : fonction pure de `(seed, speaker_key)` — seed
  documentée `zarma-benchmark-split-v1`. Un locuteur ne peut jamais apparaître
  dans deux splits. Deux exécutions → manifest identique (reproductible).
- **Fail-closed** : `build` refuse toute entrée sans vérité terrain valide,
  condition invalide ou audio manquant (`--allow-partial` pour exclure et
  poursuivre).
- L'audio de benchmark reste **hors Git** ; seuls le manifest et les scripts
  sont versionnés. Provenance & consentement : voir `dataset/benchmark/README.md`.

## Harnais d'évaluation — Exact Number Accuracy (story 5.2)

Rejoue **le même** pipeline que l'API (ASR → normalisation → parsing → confiance →
politique) sur le corpus 5.1 et exporte un rapport **versionné** (`.json` + `.md`)
dans `docs/qa/benchmarks/`. Métrique de décision = **Exact Number Accuracy** (pas
le WER). Source ASR interchangeable (NFR9), **sans GPU** en mode rejeu.

```bash
# A) Passe réelle (après story 5.3) avec dump d'hypothèses réutilisable :
uv run python scripts/bench/run_benchmark.py \
    --manifest dataset/manifests/benchmark.jsonl \
    --asr-mode ctc --audio-root dataset/benchmark \
    --dump-hypotheses dataset/benchmark/hypotheses/ctc.jsonl \
    --split test --out docs/qa/benchmarks/benchmark-ctc-test

# B) Rejeu reproductible sans GPU (recalcule le rapport depuis le dump) :
uv run python scripts/bench/run_benchmark.py \
    --manifest dataset/manifests/benchmark.jsonl \
    --hypotheses dataset/benchmark/hypotheses/ctc.jsonl \
    --split test --out docs/qa/benchmarks/benchmark-ctc-test
```

- Le rapport porte toutes les métadonnées de reproductibilité (`grammar_version`,
  `model_version`, empreinte du manifest, poids/seuils effectifs, mode ASR, version
  du harnais) ; mêmes entrées → rapport identique hors horodatage.
- **Sans PII** : agrégats + `speaker_key` anonymes ; aucun audio ni transcription
  identifiante. Les dumps d'hypothèses restent hors Git (`dataset/benchmark/**/*.jsonl`).
- **Fail-closed** : manifest introuvable/invalide, split vide ou entrées
  inexploitables sans `--allow-partial` → code de sortie non nul.

## Décodage contraint à la grammaire (story 5.6)

Le décodage CTC est restreint à la **grammaire des nombres zarma** : la sortie est
valide par construction (`0`–`1 000 000`), ou le décodeur s'abstient. L'algorithme
et ses paramètres sont documentés dans `services/asr/README.md` ; les outils de
mesure et de calibration vivent ici.

### Chaîne complète

```bash
# 1) Passe de décodage contraint sur le corpus (SEUL script exigeant l'env ASR
#    lourd : torch + omnilingual-asr, cf. scripts/bench/README-local-asr.md).
#    Produit en une fois : hypothèses contraintes, hypothèses gloutonnes,
#    observations de rejet et fixtures de logits réels pour la CI.
export DYLD_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_LIBRARY_PATH
asrenv/bin/python scripts/bench/decode_constrained.py \
    --manifest dataset/manifests/benchmark.jsonl \
    --audio-root dataset/benchmark \
    --out dataset/benchmark/hypotheses/ctc-constrained.jsonl \
    --dump-greedy dataset/benchmark/hypotheses/ctc-greedy.jsonl \
    --dump-observations dataset/benchmark/rejection/dev-observations.jsonl \
    --dump-logits services/asr/tests/fixtures

# 2) Comparaison glouton vs contraint via le harnais 5.2 (sans GPU).
#    Aucune métrique n'est réimplémentée : le harnais 5.2 est appelé deux fois.
uv run python scripts/bench/compare_decoding.py \
    --manifest dataset/manifests/benchmark.jsonl \
    --greedy dataset/benchmark/hypotheses/ctc-greedy.jsonl \
    --constrained dataset/benchmark/hypotheses/ctc-constrained.jsonl \
    --split test --out docs/qa/benchmarks/decoding-greedy-vs-constrained-v1

# 3) Calibration du seuil de rejet (JAMAIS sur le split de test — NFR10).
uv run python scripts/bench/calibrate_rejection.py \
    --observations dataset/benchmark/rejection/dev-observations.jsonl \
    --split dev --max-false-acceptance 0.02 \
    --out docs/qa/benchmarks/rejection-calibration-v1
```

### Protocole de calibration du seuil de rejet

- **Signal** : `confidence = exp(-(nll_contraint − nll_libre) / nb_tokens)` —
  coût acoustique moyen, par symbole émis, payé pour rester dans la grammaire.
  Normaliser par le nombre de **tokens** et non par la durée est délibéré :
  par trame, une courte insertion dans un long silence paraît anodine (mesuré :
  `afo` dans 40 trames de silence obtenait 0,59 par trame contre 0,001 par token).
- **Jeu de calibration** : `dev` / `calibration` uniquement. Le script est
  **fail-closed** — une seule ligne du split `test` fait échouer la calibration.
- **Observations** : chaque ligne porte `is_numeric`, vérité terrain distinguant
  les énoncés de nombres des entrées de contrôle (parole quelconque, bruit,
  silence, musique).
- **Sélection** : le plus petit seuil dont la fausse acceptation reste sous
  `--max-false-acceptance`, à rappel maximal. Si **aucun** seuil ne tient la
  contrainte, le script le dit et sort en erreur — le seuil reste à `0.0`.
  La courbe complète est publiée pour que le compromis soit lisible.
- **Application** : `DECODE_REJECT_THRESHOLD` côté service ASR, jamais en dur.

### Ce que le rapport de comparaison contient

Ventilation par **condition** (calme/bruit), **tranche de nombres** (tags
`short`/`long`/`confusion`) et **split** ; taux de décision et latences des deux
côtés ; rappel de la **référence du prototype** (Annexe A §4 de la story 5.6 :
73 % global, 79 % sur locuteur non vu) ; et l'**écart aux objectifs NFR2**
(≥ 95 % calme, ≥ 90 % bruit) calculé par condition — jamais masqué.

Les chiffres de décision se lisent sur le split `test` (locuteurs jamais vus).

## Démo moteur linguistique

```bash
uv run python scripts/zarma.py 372
```
