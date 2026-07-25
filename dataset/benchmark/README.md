# dataset/benchmark

Corpus d'**évaluation** (Epic 5) : audios étiquetés en vérité terrain, avec
**split strict par locuteur** (anti-fuite, NFR10). Ce corpus est le socle du
harnais d'évaluation (story 5.2) qui mesure l'*Exact Number Accuracy*.

## Provenance & consentement des données (AC3)

**Aucun audio non consenti n'entre dans le benchmark.** Deux sources autorisées :

1. **Contributions consenties de l'Epic 4** — les `contributions` `validated`
   (voir story 4.5), déjà anonymisées par `speaker_key` et hors base. Elles
   peuvent être réutilisées pour l'évaluation.
2. **Corpus-graine consenti** — enregistrements collectés spécifiquement pour
   l'évaluation, avec le même consentement explicite (FR19/FR20).

L'audio brut/enregistré **reste hors Git** (git-ignored, comme `dataset/raw/`).
Seuls le **manifest** (`dataset/manifests/`) et les **scripts** sont versionnés.
Le manifest ne contient ni identité, ni chemin absolu — uniquement une référence
audio opaque relative, la vérité terrain et des métadonnées non identifiantes.

## Contenu attendu (AC1)

- ≥ 100 audios, **plusieurs locuteurs** ;
- nombres **courts** (unités/dizaines) **et longs** (centaines → million) ;
- **paires de confusion** connues, dérivées de `asr_confusions` (source unique).
- conditions **calme** et **bruit**.

## Schéma du manifest (JSONL, une ligne par audio)

| Champ             | Type           | Description                                         |
|-------------------|----------------|-----------------------------------------------------|
| `audio_path`      | string         | Référence audio **opaque relative** (jamais absolue).|
| `expected_number` | int            | Vérité terrain (0–1 000 000).                       |
| `expected_prompt` | string         | Forme canonique `generate(expected_number)`.        |
| `speaker_key`     | string         | Locuteur anonyme (dérivation non réversible).       |
| `region`          | string \| null | Région coarse si connue.                            |
| `condition`       | string         | `calme` \| `bruit`.                                 |
| `split`           | string         | `test` \| `dev` (strict par locuteur).              |

## Reproduction (AC4)

Voir `scripts/README.md` (section benchmark) : le split par locuteur est une
fonction pure de `(seed, speaker_key)` — seed documentée
`zarma-benchmark-split-v1` — donc un même locuteur tombe toujours dans le même
split et n'apparaît jamais dans deux splits. Deux exécutions sur les mêmes
entrées produisent un manifest identique.
