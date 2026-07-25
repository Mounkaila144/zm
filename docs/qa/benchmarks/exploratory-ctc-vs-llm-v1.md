# Constat exploratoire — CTC vs LLM sur un premier locuteur (`v1`)

> ⚠️ **Ceci n'est PAS le document de décision de la story 5.4.** Échantillon trop
> petit (**1 locuteur, 18 fichiers**) pour trancher le modèle du MVP : aucun split
> par locuteur possible (NFR10), aucune condition « bruit ». Il s'agit d'un
> **test de faisabilité** dont les enseignements alimentent les stories 5.4 et 5.5.

## Protocole

| Élément | Valeur |
|---|---|
| Corpus | 18 WAV mono 16 kHz, 1 locuteur, condition calme, nombres 0–20 (14/15/17 absents) |
| Vérité terrain | convention `v1-N.wav` = nombre `N` (fournie par le locuteur) |
| Modèle A | `omniASR_CTC_300M_v2` — local (MacBook M1, CPU), **sans** `lang` |
| Modèle B | `omniASR_LLM_300M_v2` — Google Colab (T4), `lang=["dje_Latn"]` |
| Pipeline | harnais 5.2 en mode rejeu (`run_benchmark.py --hypotheses`) |
| Hypothèses | `dataset/benchmark/hypotheses/v1-{ctc-local,llm-colab}.jsonl` (hors Git) |

## Résultats

| Métrique | CTC | LLM + `dje_Latn` |
|---|---|---|
| Sorties en alphabet latin | ~5/18 | **16/18** |
| Exact Number Accuracy | 1/18 (0,056) | 2/18 (0,111) |
| Transcriptions ≥70 % similaires au canonique | — | **13/18** |

## Enseignements

1. **Le CTC ignore l'indication de langue.** Vérifié empiriquement : passer
   `lang=["dje_Latn"]` au CTC ne change **strictement rien** à sa sortie. Il
   auto-détecte le script et, sur des extraits courts (chiffres isolés < 1 s), se
   trompe souvent → transcriptions en chinois/arabe, inexploitables.

2. **Le LLM corrige le problème de script.** Avec `lang=["dje_Latn"]`, 16/18 des
   sorties sont en zarma latin. C'est l'argument décisif en faveur du LLM pour des
   énoncés courts — cas d'usage central du produit.

3. **L'écart résiduel est orthographique, pas acoustique.** Le LLM entend juste,
   mais écrit selon d'autres conventions que le lexique :

   | LLM | Canonique | Écart |
   |---|---|---|
   | `i wey` | `iwey` | segmentation (une espace) |
   | `yamo` | `yaamo` | voyelle longue |
   | `i way cindi hinka` | `iwey cindi hinka` | `way` / `wey` |
   | `i gu` | `igou` | segmentation + `u`/`ou` |

   → Matière directe pour la **story 5.5** (table de variantes linguistiques et
   `asr_confusions`). Enrichir ces variantes relèverait fortement l'accuracy sans
   toucher au modèle. **À faire sur un protocole dédié**, jamais pour « gonfler »
   un score de benchmark.

4. **Contrainte matérielle.** CTC (checkpoint 1,24 Go) tourne localement sur M1/8 Go
   (pic ~1,75 Go, ~0,6 s/clip en CPU). LLM (6,2 Go) nécessite un GPU externe —
   validé sur Colab T4 (~150–370 ms/clip).

## 🔑 Découverte décisive — le problème est le DÉCODAGE, pas le modèle

Après consultation externe et **vérification empirique**, la cause racine est
identifiée : le pipeline officiel d'Omnilingual fait un **décodage glouton**.

Code source (`omnilingual_asr/models/inference/pipeline.py`, lignes 316-317) :

```python
logits, bl_out = self.model(batch.source_seqs, batch_layout)
pred_ids = torch.argmax(logits, dim=-1)      # ← argmax trame par trame
```

Un modèle CTC émet, à chaque trame, une distribution sur **tout** son vocabulaire
de sortie (**10 288 tokens**, dont seulement ~1 122 latins). Sur un clip court,
les caractères chinois/arabes peuvent l'emporter d'un cheveu — **mais les chemins
latins existent toujours dans les logits**.

### Expérience : décodage contraint à la grammaire

Prototype : `scripts/bench/constrained_decode_prototype.py`. On capture les
logits, puis on score chaque nombre candidat (forme canonique issue de
`zarma_numbers.generate`) via `ctc_loss`, et on retient le meilleur.

| Stratégie de décodage | Exact Number Accuracy |
|---|---|
| Glouton (pipeline officiel) | **1/18** |
| Contraint, score brut | 10/18 |
| **Contraint + normalisation par longueur** | **18/18** |

La normalisation par longueur est **indispensable** : sans elle, le biais du CTC
vers les séquences courtes fait converger 6 cas sur `afo`.

**Même modèle (1,24 Go), même audio, aucun entraînement, CPU sur MacBook M1.**

### Conséquences

1. **Le LLM 6,2 Go n'est pas nécessaire.** Son seul avantage réel (respecter
   `lang=`) devient inutile : la contrainte de grammaire est plus forte et plus
   sûre. → Pas de GPU obligatoire, hébergement CPU scale-to-zero envisageable,
   voire embarqué à terme (le CTC quantisé descend vers ~300-400 Mo).
2. **Le problème orthographique disparaît par construction** : seules les formes
   canoniques sont des sorties possibles. Les variantes (`way`/`wey`, `u`/`ou`)
   s'ajoutent comme **prononciations alternatives** d'un même token, pas comme
   corrections floues en aval.
3. **Compatible NFR14** : ce n'est pas du fuzzy matching (aucune distance
   d'édition textuelle), mais une recherche acoustique sur un espace de sorties
   valides. Toute sortie est parseable par le moteur déterministe.

### Validation multi-locuteurs (99 fichiers, 3 locuteurs)

Corpus étendu : **3 locuteurs** (`v1`, `v2`, `v3`), **99 fichiers** exploitables,
**52 nombres distincts** de 0 à 10 000 (dont 372, 250, 1000, 2000, 10000).
Fichiers exclus : `v2-.wav` (pas de vérité terrain dans le nom). Anomalie signalée :
`v3-0/1/2.wav` se trouvent dans le dossier `v2` (locuteur attribué par dossier).

Deux tailles d'espace de recherche, pour mesurer la robustesse au passage à l'échelle :

| Locuteur | n | Glouton | Contraint (52 candidats) | Contraint (**1010 candidats**) |
|---|---|---|---|---|
| v1 | 39 | 1/39 (3 %) | 30/39 (77 %) | 29/39 (74 %) |
| v2 | 27 | 1/27 (4 %) | 19/27 (70 %) | 17/27 (63 %) |
| v3 | 33 | 0/33 (0 %) | 28/33 (85 %) | 26/33 (79 %) |
| **TOTAL** | **99** | **2/99 (2 %)** | **77/99 (78 %)** | **72/99 (73 %)** |

**Robustesse au passage à l'échelle** : multiplier l'espace de recherche par ~20
(52 → 1010 candidats) ne coûte que **5 points** (78 % → 73 %). Le score acoustique
discrimine réellement ; ce n'est pas un artefact d'un petit ensemble de candidats.

### Calibration du paramètre de normalisation (protocole propre)

Le score retenu est `ctc_loss(candidat) / longueur^p`. Le paramètre `p` a été
**calibré sur v1+v2** puis évalué sur **v3 tenu à l'écart** (split par locuteur,
NFR10 — pas de fuite méthodologique).

| p | v1+v2 (calibration) | v3 (test, voix jamais vue) |
|---|---|---|
| 0.0 (score brut) | 45 % | 52 % |
| 0.5 | 61 % | 67 % |
| **1.0** | **70 %** | **79 %** |
| 1.2 | 68 % | 67 % |
| 2.0 | 35 % | 36 % |

`p = 1.0` est un **optimum net**. Sans normalisation (`p=0`), le biais du CTC vers
les séquences courtes fait converger les réponses vers `afo`.

**Point vérifié et écarté** : l'hypothèse d'un mauvais indice de *blank* CTC a été
testée (`blank=1` = `pad_idx` du tokenizer) — elle **dégrade** massivement
(0–21 %). `blank=0` est bien correct pour ce modèle.

### Résultat de référence

> **Décodage contraint, blank=0, p=1.0, espace de 1010 candidats :**
> **79 % sur un locuteur jamais entendu**, 73 % toutes voix confondues,
> contre **2 %** en décodage glouton. Modèle CTC 1,24 Go, CPU, MacBook M1.

### Écart aux objectifs de bêta

Les objectifs NFR2 (≥ 95 % calme, ≥ 90 % bruit modéré) **ne sont pas atteints**
(73–79 % en condition calme). L'écart restant provient majoritairement de nombres
**courts** appariés à des candidats **longs**. Leviers identifiés, par ordre de
rendement attendu :

1. **Vrai décodeur en faisceau** sur automate/trie (`pyctcdecode`, flashlight) au
   lieu de l'énumération + rescoring : gère nativement la contrainte de grammaire.
2. **Modélisation de durée** : un extrait de 0,7 s ne peut pas contenir
   `zangou hinka nda wayhakkou cindi hinka`. Pénaliser l'incohérence entre le
   nombre de trames et la longueur attendue du candidat (principe acoustique, pas
   du fuzzy matching).
3. **Fine-tuning** sur le corpus consenti, avec les formes canoniques comme
   étiquettes — le levier de fond.

### Ce qui reste à construire (non couvert par le prototype)

- **Recherche en faisceau sur automate/trie** de la grammaire, au lieu de
  l'énumération : ici le choix se fait parmi **21 candidats** (0–20) ; en
  production l'espace est 0–1 000 000. Piste : `pyctcdecode` ou décodeur
  flashlight avec lexique + grammaire.
- **Mécanisme de rejet obligatoire** : le décodage contraint garantit la
  *validité*, **pas** la *correction*. Sans seuil, un bruit produirait un nombre
  valide. Comparer le score contraint au score libre (ou la probabilité
  normalisée) et basculer en `repeat` au-delà d'un seuil calibré. Ce signal
  s'intègre naturellement dans la confiance composite existante (`confidence.py`)
  et la politique `accept/confirm/repeat` (`policy.py`).
- **Validation multi-locuteurs** et en condition bruitée.

## Limites

- **1 seul locuteur** → aucune mesure de généralisation possible (NFR10).
- Le 18/18 est obtenu sur un **choix parmi 21 candidats**, pas sur l'espace
  complet 0–1 000 000 : il valide l'approche, il ne prédit pas la performance en
  production.
- **Condition calme uniquement** → objectif « bruit modéré » non évalué.
- 18 fichiers, nombres 0–20 → ni nombres longs, ni paires de confusion couverts.
- Les scores acoustiques ne sont pas fournis par l'API haut-niveau d'Omnilingual
  (`acoustic_score` fixé à 1.0) → les taux accept/confirm/repeat ne sont pas
  interprétables ici ; seule l'Exact Number Accuracy fait foi.

## Suite

- **5.4** reste à faire avec un corpus multi-locuteurs (voir plan de la story 5.1).
- **5.5** : enrichir variantes/`asr_confusions` à partir des écarts observés.
