# docs/qa/benchmarks

Rapports **versionnés** du harnais d'évaluation (story 5.2).

Chaque exécution de `scripts/bench/run_benchmark.py` écrit deux fichiers de même
base :

- `<nom>.json` — source machine des chiffres (clés triées, reproductible) ;
- `<nom>.md` — rapport lisible (Exact Number Accuracy, ventilations, top paires de
  confusion, taux, latences).

Ces rapports sont **sans PII** (agrégats + `speaker_key` déjà anonymes ; aucun
audio, aucune transcription identifiante) et portent toutes les métadonnées de
reproductibilité : `grammar_version`, `model_version`, empreinte SHA-256 du
manifest, poids de confiance et seuils de politique effectifs, mode ASR et version
du harnais. Seul le champ `generated_at` (horodatage) varie d'une exécution à
l'autre pour des entrées identiques.

Les **dumps d'hypothèses ASR** (sorties brutes rejouables) restent **hors Git**
(`dataset/benchmark/**/*.jsonl`) — voir `scripts/README.md`.
