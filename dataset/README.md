# dataset

Données audio & manifestes du projet.

- `raw/` — audio brut **consenti** (git-ignored, jamais committé).
- `manifests/` — manifeste versionné, split par locuteur.
- `benchmark/` — corpus d'évaluation (Epic 5) ; audio hors Git, voir
  [`benchmark/README.md`](benchmark/README.md). Constitution reproductible via
  `scripts/bench/build_benchmark_corpus.py` (story 5.1).

L'audio consenti vit sous `AUDIO_STORAGE_DIR` (hors base, hors Git). Le manifest
est un artefact **dérivé** et versionné : il ne référence que des noms de
fichiers opaques relatifs, jamais l'audio brut ni un chemin absolu.

## Manifest dataset (story 4.5)

Généré par `scripts/build_dataset_manifest.py`. Fichier JSONL, une contribution
par ligne.

### Prédicat d'éligibilité

Un **unique** prédicat sélectionne les contributions exportables :

```
status = 'validated' AND audio_ref IS NOT NULL
```

Les états `pending`, `rejected` et `withdrawn` sont donc systématiquement exclus.
Chaque audio est en outre vérifié avant publication : présence, lisibilité et
format canonique (WAV mono 16 kHz PCM16).

### Schéma d'une ligne

| Champ             | Type          | Description                                            |
|-------------------|---------------|--------------------------------------------------------|
| `audio_path`      | string        | Référence audio **opaque relative** (jamais absolue).  |
| `expected_number` | int           | Nombre attendu (0–1 000 000).                          |
| `speaker_key`     | string        | Clé locuteur (dérivation non réversible, non PII).     |
| `region`          | string \| null | Région coarse si connue, sinon `null`.                |
| `split`           | string        | `train` \| `dev` \| `test`.                            |

Le manifest ne contient **jamais** `anon_id`, `device_info`, chemin absolu ni
audio brut.

### Split par locuteur

Le split est groupé par `speaker_key` et reproductible par seed
(`DEFAULT_SPLIT_SEED = "zarma-dataset-split-v1"`, surchargée par `--seed`).
L'affectation ne dépend que de `(seed, speaker_key)` : un même locuteur tombe
toujours dans le même split, et ajouter de nouveaux locuteurs ne déplace jamais
les existants. Répartition par défaut : `train` 0.8, `dev` 0.1, `test` 0.1. Un
locuteur ne peut donc **jamais** apparaître dans deux splits.

### Reproductibilité et retrait

- Écriture **atomique** (fichier temporaire puis renommage) ; sortie triée de
  façon stable → deux exécutions produisent un contenu identique.
- **Fail-closed** : par défaut, une seule entrée invalide empêche toute écriture
  (aucun manifest partiel). `--allow-partial` publie uniquement les entrées
  valides et rapporte les exclusions.
- **Retrait / reconstruction** : après un retrait (story 4.4), les contributions
  `withdrawn` perdent leur `audio_ref` et sortent de fait du prédicat. Il suffit
  de régénérer le manifest (`build_dataset_manifest.py`) pour obtenir une version
  à jour, purgée des données retirées.
