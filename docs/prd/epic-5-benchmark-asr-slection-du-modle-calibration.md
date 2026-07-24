# Epic 5 — Benchmark ASR, sélection du modèle & calibration

**Objectif étendu :** transformer le choix du modèle vocal et le réglage de la confiance en décisions fondées sur les données. À la fin de cet epic, un corpus de benchmark reproductible (split strict par locuteur) permet de comparer CTC vs LLM sur l'Exact Number Accuracy, de produire une matrice de confusions, de sélectionner le modèle du MVP, de brancher le recognizer réel via l'interface existante, et de calibrer les poids/seuils de la confiance composite. Cet epic est **gaté par la décision de ressource GPU** (risque n°1) ; tout ce qui précède peut être livré via `MockRecognizer`.

> **Décision requise (bloquante pour cet epic) :** ressource GPU pour l'ASR — cloud (fournisseur/budget) vs machine locale. Le Mac M1 8 Go ne peut pas servir l'ASR de production.

## Story 5.1 — Corpus de benchmark avec split par locuteur

En tant que responsable données,
je veux un corpus d'évaluation propre et représentatif,
afin de mesurer la qualité sans fuite de données.

### Acceptance Criteria

1. Le corpus contient ≥ 100 audios, plusieurs locuteurs, nombres courts/longs et paires de confusion.
2. Le jeu de test est séparé **par locuteur** : aucune voix de test n'apparaît ailleurs.
3. Chaque audio est étiqueté avec le nombre attendu (vérité terrain) et des métadonnées (locuteur anonyme, région si connue, condition calme/bruit).
4. Le corpus est reproductible (script de constitution + manifest versionné).

## Story 5.2 — Harnais d'évaluation Exact Number Accuracy

En tant qu'ingénieur,
je veux un harnais d'évaluation automatisé,
afin de comparer objectivement les modèles.

### Acceptance Criteria

1. Le harnais exécute le pipeline complet (ASR → normalisation → parsing) sur le corpus et calcule l'**Exact Number Accuracy** (métrique de décision, pas le WER).
2. Il produit une **matrice de confusions** des nombres et met en évidence les paires proches.
3. Il mesure les taux de rejet / fausse acceptation et la latence ASR.
4. Les résultats sont reproductibles et exportés (rapport versionné).

## Story 5.3 — Intégration des recognizers réels (CTC & LLM)

En tant qu'ingénieur,
je veux brancher les modèles Omnilingual réels derrière l'interface existante,
afin de les évaluer sans modifier l'API ni l'app.

### Acceptance Criteria

1. Les implémentations CTC (`omniASR_CTC_300M_v2`, sans `lang`) et LLM (`omniASR_LLM_300M_v2`, `lang=["dje_Latn"]`) respectent l'interface `SpeechRecognizer`.
2. Le service ASR se déploie/redémarre indépendamment de l'API (image Docker ASR lourde séparée).
3. Le passage de Mock à un modèle réel se fait par configuration, sans changement d'API ni de mobile.
4. Un test de fumée confirme une reconnaissance réelle de bout en bout sur la ressource GPU retenue.

## Story 5.4 — Sélection du modèle du MVP

En tant que responsable produit,
je veux choisir le modèle sur des données,
afin d'ancrer la décision dans des preuves reproductibles.

### Acceptance Criteria

1. CTC et LLM sont comparés sur l'Exact Number Accuracy en conditions calme et bruit modéré (locuteurs non vus).
2. La décision documentée retient le modèle du MVP avec justification chiffrée et matrice de confusions à l'appui.
3. Les objectifs de bêta (≥ 95 % calme, ≥ 90 % bruit modéré) sont évalués et l'écart éventuel est documenté avec plan.
4. La configuration par défaut de l'API pointe vers le modèle retenu.

## Story 5.5 — Calibration de la confiance composite

En tant qu'ingénieur,
je veux calibrer les poids et seuils de confiance sur des données réelles,
afin d'optimiser le compromis acceptation / confirmation / rejet.

### Acceptance Criteria

1. Les poids (acoustique, grammatical, variante, marge, historique de confusions) et les seuils accepter/confirmer/répéter sont réglés à partir du corpus.
2. La table de confusions ASR est alimentée par les erreurs réelles observées (distincte des variantes linguistiques).
3. Le réglage améliore (ou documente le compromis) le taux de fausse acceptation sans dégrader excessivement l'acceptation correcte.
4. Les valeurs calibrées sont versionnées et rechargées par l'API sans changement de code applicatif.

---
