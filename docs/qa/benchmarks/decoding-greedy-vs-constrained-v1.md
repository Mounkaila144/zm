# Décodage glouton vs contraint — split `test`

> ⚠️ **RAPPORT PÉRIMÉ — à re-mesurer.** Ces chiffres ont été obtenus avec
> `grammar_version` **1.1.0**, avant la correction du connecteur validée par le
> locuteur natif (`nda` variante libre → `da`/`di` en distribution complémentaire,
> + élision `iwey`→`wey` ; `grammar_version` **1.2.0**).
>
> Conséquences connues, à ne pas ignorer en lisant les chiffres ci-dessous :
>
> - la **vérité terrain a changé** pour 8 des 96 audios (le manifest a été
>   régénéré ; son sha256 ne correspond plus à celui cité ici) ;
> - 4 audios (`v2-102`, `v2-103`, `v2-104`, `v2-110`) ont été **enregistrés avec
>   des formes désormais invalides** (`zangou nda hinka` au lieu de
>   `zangou di hinka`) : le décodeur contraint devra forcer `di` sur un audio qui
>   dit `nda`. Une dégradation ou un rejet est attendu sur ces 4 — idéalement,
>   les **ré-enregistrer** avant la re-mesure ;
> - les 4 autres écarts sont bénins (`nda` → `da`, absorbé par la table de
>   prononciations).
>
> La re-mesure exige l'environnement ASR lourd
> (`scripts/bench/decode_constrained.py`, cf. `scripts/README.md`).

- **Protocole** : comparaison 5.6.0 · harnais 5.2 `5.2.0` (aucune métrique réimplémentée)
- **grammar_version** : 1.1.0 *(périmée — voir l'avertissement ci-dessus)*
- **Manifest** : `benchmark.jsonl` (sha256 `f652a7885340…`, 96 audios) *(régénéré depuis)*

## Exact Number Accuracy

| décodage | accuracy | correct/total |
|---|---|---|
| glouton | 0.0208 | 2/96 |
| **contraint** | **0.8958** | 86/96 |
| **gain** | **+0.8750** | — |

### Par condition

| groupe | glouton | contraint | gain |
|---|---|---|---|
| calme | 0.0208 | 0.8958 | +0.8750 |

### Par tranche de nombres (tag)

| groupe | glouton | contraint | gain |
|---|---|---|---|
| confusion | 0.0000 | 0.8125 | +0.8125 |
| long | 0.0000 | 0.8696 | +0.8696 |
| short | 0.0274 | 0.9041 | +0.8767 |

### Par split

| groupe | glouton | contraint | gain |
|---|---|---|---|
| test | 0.0208 | 0.8958 | +0.8750 |

## Comparaison à la référence du prototype (Annexe A §4)

- corpus de référence : 3 locuteurs, 99 fichiers, 52 nombres distincts (0→10 000), condition calme
- glouton mesuré alors : 0.02 · contraint : 0.73 (locuteur non vu : 0.79)
- ici (contraint, split `test`) : **0.8958**
- note : espace de recherche 1010 candidats énumérés ; le décodeur 5.6 couvre 0–1 000 000

## Écart aux objectifs NFR2

| condition | cible | mesuré | écart | atteint |
|---|---|---|---|---|
| bruit | 0.90 | — | — | — |
| calme | 0.95 | 0.8958 | -0.0542 | ❌ |

## Taux de décision

| taux | glouton | contraint |
|---|---|---|
| rejet | 0.9792 | 0.0000 |
| fausse acceptation | 0.0000 | 0.0000 |
| confirmation | 0.0000 | 0.8750 |
| acceptation correcte | 0.0208 | 0.1250 |

