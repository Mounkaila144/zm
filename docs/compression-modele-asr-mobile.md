# Compression du modèle ASR pour l'embarquer sur mobile

> **Statut : travail futur, non commencé.** Ce document conserve l'analyse et le
> plan pour ne pas avoir à les refaire. Rédigé le 2026-07-29, après
> l'entraînement du modèle v1 et sa comparaison à Omnilingual.

## Le problème

Le modèle v1 fait **94 Mo une fois quantifié en int8**. C'est trop lourd pour la
cible : téléphones Android d'entrée de gamme au Niger, utilisateurs qui paient
leurs données au mégaoctet, fonctionnement entièrement hors ligne.

**Objectif : 3 à 10 Mo, en conservant ~95 % de nombres exacts.**

## Point de départ — ce qui est mesuré

Le modèle v1 (`research/zarma-assistant/scripts/train_asr_v1_colab.py`) :
wav2vec2-base affiné en CTC caractère, 30 symboles, blank = 0.

| | paramètres | |
|---|---|---|
| convolutions (gelées) | 4,2 M | |
| projection + position | 5,1 M | |
| 12 couches transformer | 85,05 M | **90 % du modèle** |
| tête CTC | 0,02 M | |
| **total** | **94,4 M** | 378 Mo fp32, **94 Mo int8** |

Performance mesurée en leave-one-voice-out sur les 8 personnes du corpus
(découpage par **voix**, jamais par fichier) : **95,1 % de nombres exacts**
(min 89,6 %, max 100 %), CER 2,0 %. Voir `docs/` et l'historique des runs.

## Pourquoi comprimer le modèle existant ne suffira pas

La base non-transformer (conv + projection + position) pèse 9,3 M paramètres à
elle seule. Retirer des couches donne un plancher structurel :

| couches transformer gardées | paramètres | taille int8 |
|---|---|---|
| 12 (actuel) | 94,4 M | 94 Mo |
| 6 | 52 M | ~52 Mo |
| 4 | 38 M | ~38 Mo |
| 2 | 23,5 M | **~23 Mo — plancher** |

Deux techniques à **écarter** :

- **Élagage non structuré** (type PARP) : 90 % de sparsité ne réduit pas la
  taille du fichier TFLite/ONNX sans runtime sparse, qu'on n'aura pas sur les
  appareils visés.
- **int4** : mal supporté par TFLite et fragile sur un modèle déjà petit.

## Les trois options

### Option 1 — Distillation vers un petit CNN (recommandée)

**Principe.** Le modèle v1 devient le **professeur**. On entraîne à côté un
**élève** bien plus petit — réseau convolutif 1D à convolutions séparables, type
QuartzNet / MatchboxNet, 2 à 5 M de paramètres, sans attention — à reproduire
les sorties du professeur trame par trame.

**Pourquoi ça lève la contrainte des données.** Les 12 minutes de corpus ne
limitent plus l'élève : on déforme les 545 clips à volonté (bruit, vitesse,
réverbération, timbre) et le professeur produit sa réponse sur chaque variante.
L'élève voit un flux quasi infini de paires (audio, distribution cible) au lieu
de 545 exemples étiquetés.

**Architecture visée.** Log-mel 40-64 bandes (25 ms / 10 ms) → blocs de
convolutions 1D depthwise-séparables avec résidus → **stride total 2 pour sortir
des trames à 20 ms**, soit exactement la cadence de wav2vec2 (indispensable pour
la distillation trame à trame) → tête linéaire vers les 30 symboles, blank = 0.

**Perte.** `L = λ·CTC(transcription) + (1−λ)·T²·KL(professeur ‖ élève)` sur les
logits par trame, avec `T ≈ 2-4` et `λ ≈ 0,3-0,5`.

**Augmentation à ajouter** (au-delà de celle du v1) : perturbation de
formants / VTLP (`parselmouth`) — c'est ce qui simule de **nouvelles voix**,
la vraie faiblesse du corpus ; plus réverbération et simulation de codec
AMR/opus.

| | |
|---|---|
| taille attendue | **2-5 Mo int8** |
| pic RAM attendu | < 30 Mo |
| précision **estimée** | 92-95 % |
| effort | 2-3 jours pour le pipeline, puis itérations |

### Option 2 — Troncature + réaffinage (expérience de mesure)

Garder les couches 1..k (k = 2, 4, 6), réinitialiser la tête CTC, réappliquer la
recette du v1 (encodeur gelé 400 pas, lr encodeur 5e-5, lr tête 1e-3).

**Ce n'est pas la solution finale** (23-38 Mo), mais c'est l'expérience la moins
chère qui existe : elle trace la courbe capacité → précision et dit combien de
« cerveau » la tâche exige réellement. **Si k = 2 tient déjà ~93 %, l'option 1
est quasi gagnée d'avance.** Un modèle tronqué fait aussi un professeur moins
coûteux à faire tourner pendant la distillation.

Précision attendue : ~93-95 % pour k = 4 ; k = 2 est l'inconnue intéressante.

### Option 3 — Modèle ultra-mini (à tenter seulement si l'option 1 réussit)

Même recette que l'option 1 mais taille BC-ResNet / TC-ResNet : 200 k à 1 M de
paramètres, soit **0,3 à 1,5 Mo**.

La littérature keyword spotting montre que 100-300 k paramètres suffisent pour
35 mots à ~98 % — **mais avec des milliers de locuteurs à l'entraînement**. Ici
le facteur limitant n'est pas le vocabulaire, c'est la généralisation
inter-locuteurs à partir de 8 voix. À n'essayer que si l'option 1 tient ≥ 94 %,
en descendant par paliers (5 M → 2 M → 800 k) jusqu'à voir le score plier.

## Ordre des expériences

**Astuce de criblage :** ne pas lancer les 8 replis pour chaque essai. Utiliser
**2 replis sentinelles** — la pire voix (v2, 89,6 %) et une voix moyenne — soit
~15 min par configuration au lieu d'une heure. Le leave-one-voice-out complet ne
sert qu'à valider les finalistes.

1. **Jour 1 — troncature k = 6/4/2** (option 2, pipeline existant).
   Livrable : la courbe capacité → précision.
2. **Jours 2-4 — pipeline de distillation.** Vérifier d'abord que l'élève *sans*
   distillation (CTC seule sur données augmentées) ne s'effondre pas, puis
   ajouter la KL et mesurer le gain apporté.
3. **Jours 5-7 — descente en taille** : 5 M → 3 M → 1,5 M sur les 2 sentinelles ;
   s'arrêter un cran au-dessus du point de rupture. LOOVO complet sur le
   finaliste.
4. **Quantification et appareil** : int8 post-entraînement d'abord ; si la perte
   dépasse 1 point, quantization-aware training (quelques époques suffisent sur
   un modèle convolutif). Export TFLite, puis mesure sur un vrai téléphone
   d'entrée de gamme : score final **avec le décodeur contraint**, pic RAM,
   latence.

## Prérequis à ne pas oublier

**Les modèles professeurs n'existent pas.** `train_asr_v1_colab.py` entraîne
chaque repli puis jette les poids — aucun `save_pretrained` n'a jamais été
appelé. Avant toute distillation, il faut **relancer les 8 replis en
sauvegardant les poids** (~1 h de Colab), ou ajouter un `--save-model` au script.

**Protocole honnête.** Distiller **par repli** : le professeur d'un repli n'a
jamais entendu la voix testée. Le modèle de production final, lui, sera distillé
depuis un professeur entraîné sur les 8 voix.

**Compatibilité obligatoire.** La sortie doit rester des logits CTC sur un
vocabulaire de tokens avec **blank = 0**, pour rester utilisable par
`services/asr/app/decoding.py` sans le réécrire. Le CER brut de l'élève sera
pire que celui du professeur — **c'est normal et sans importance** : la seule
métrique qui compte est le nombre exact après décodage contraint.

## Le plafond réel

Attendre **93-95 % pour 3-6 Mo**. Si le score plafonne à 91-92 %, le levier le
plus rentable n'est **pas** d'ajouter des paramètres, mais d'ajouter de la
**diversité de voix** — perturbation de formants, voire conversion de voix.

C'est la contrainte des **8 locuteurs**, pas celle des 12 minutes, qui fixe le
plafond. La voix v2 (89,6 %) est le canari : c'est elle qui cassera en premier.

## Bibliographie

**Distillation de modèles SSL** — utiles pour leurs *techniques* (distillation
de représentations intermédiaires, initialisation de l'élève depuis des couches
du professeur), mais **pas comme solution** : tous ≥ 20 Mo en int8, car conçus
pour rester généralistes — la contrainte que notre tâche fermée permet
justement d'abandonner.

- DistilHuBERT — Chang et al., 2022 (~23,5 M)
- FitHuBERT — Lee et al., 2022 (~22,5 M)
- LightHuBERT — Wang et al., 2022 (small ~27 M ; coût d'entraînement hors de
  portée de Colab)

**Élagage** — PARP, Lai et al., NeurIPS 2021 : élagage de wav2vec2 pour l'ASR
peu doté. À lire pour comprendre, pas pour déployer (sparsité non structurée).

**Architectures cibles (options 1 et 3)**

- MatchboxNet — Majumdar & Ginsburg, 2020 (93 k paramètres, 97,5 % sur 35 mots)
- BC-ResNet — Kim et al., 2021 (321 k, ~98,7 %)
- TC-ResNet ; Speech Commands — Warden, 2018
- QuartzNet — Kriman et al., 2020 (6,7 M) : la version CTC pleine phrase

**Distillation pour CTC** — Takashima et al., 2018 (niveau séquence). En
pratique, KL trame à trame + CTC combinées suffisent.

**Cas le plus proche du nôtre** — « radio browsing » keyword spotting pour le
luganda et le somali (Menon, van Niekerk, de Wet et al., UN Global Pulse) :
petits vocabulaires, très peu de données, langues africaines. Peu de chiffres
transposables directement, mais même conclusion — petits CNN + augmentation
massive.

**Augmentation** — SpecAugment (Park et al., 2019), perturbation de vitesse
(Ko et al., 2015), VTLP (Jaitly & Hinton, 2013), bruits MUSAN.

## Origine de cette analyse

Analyse produite par Fable 5 à partir de
`docs/prompt-fable-compression-modele-asr.txt`, relue et annotée. Les chiffres de
taille et de performance du modèle v1 sont **mesurés** ; les précisions attendues
des options 1 à 3 sont des **estimations non vérifiées**.
