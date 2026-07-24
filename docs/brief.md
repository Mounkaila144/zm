# Project Brief: Zarma — Reconnaissance des nombres prononcés en zarma

**Version :** 1.0
**Date :** 23 juillet 2026
**Auteur :** Mary (Business Analyst, BMAD)
**Source principale :** `docs/specification-complete-application-nombres-zarma.md`
**Statut :** Brouillon pour revue

---

## Executive Summary

**Zarma** est une application mobile qui reconnaît un nombre entier prononcé en zarma (langue à faibles ressources, code `dje_Latn`) et le restitue en chiffres. L'utilisateur appuie sur un bouton microphone, prononce un seul nombre entre `0` et `1 000 000`, et reçoit en retour la transcription, le texte zarma normalisé, le nombre compris et un niveau de confiance — avec demande de confirmation en cas d'ambiguïté plutôt qu'une invention de résultat.

Le **problème central** est l'absence d'outils numériques adaptés au zarma, une langue parlée par des millions de personnes mais quasi absente des technologies vocales. La reconnaissance directe des nombres est un cas d'usage à forte valeur (commerce, saisie, éducation, accessibilité) et un point d'entrée réaliste pour bâtir progressivement un écosystème vocal zarma.

La **cible** est double : les locuteurs zarma d'Afrique de l'Oude (principalement Niger — Niamey, Dosso et au-delà) comme utilisateurs finaux, et les contributeurs/linguistes qui valident la langue et enrichissent le corpus vocal.

La **proposition de valeur clé** repose sur une architecture hybride et prudente : **un modèle vocal multilingue déjà entraîné (Meta Omnilingual ASR) + un petit lexique zarma validé par des locuteurs + une grammaire déterministe + les corrections utilisateur + une collecte progressive**. Ce n'est pas une IA construite de zéro, mais une combinaison réaliste, testable et évolutive, adaptée à une langue peu dotée.

---

## Problem Statement

**État actuel et points de douleur.** Le zarma ne dispose quasiment d'aucun outil numérique de reconnaissance vocale. Les solutions génériques (assistants vocaux, dictées) ne le supportent pas, ou le traitent en le faisant transiter par le français — ce qui déforme les sons propres au zarma et confond des formes acoustiquement proches mais numériquement très différentes :

```text
hinka (2) / hinza (3)
iyye (7) / yega (9)
iddu (6) / iyye (7)
```

Une seule lettre change, mais le nombre change complètement. Un moteur français « approximatif » produit donc des erreurs graves et silencieuses.

**Impact.** Pour une langue à tradition largement orale, l'incapacité à saisir un nombre par la voix ferme la porte à de nombreux usages quotidiens (commerce, comptage, éducation numérique, accessibilité pour les personnes peu alphabétisées). Plus largement, l'absence de ressources linguistiques numériques (lexique validé, grammaire formalisée, corpus vocal) freine tout développement futur d'applications zarma.

**Pourquoi les solutions existantes échouent.**
- Les moteurs vocaux grand public n'incluent pas le zarma comme langue directe.
- Le passage par le français introduit des confusions systématiques et non récupérables.
- Une approche « base de données de tous les nombres » (1 000 001 lignes) est ingérable, non maintenable et n'apporte aucune robustesse grammaticale.
- Le fuzzy matching aveugle (distance de Levenshtein) transforme des erreurs mineures de transcription en erreurs numériques majeures.

**Urgence et importance.** Meta a récemment publié Omnilingual ASR, qui annonce officiellement le support du zarma (`dje_Latn`) parmi plus de 1 600 langues sous licence Apache 2.0. Cette disponibilité crée une fenêtre d'opportunité : il devient possible de construire un moteur zarma sérieux sans entraîner un modèle depuis zéro. Par ailleurs, les locuteurs natifs nécessaires à la validation linguistique sont accessibles maintenant, ce qui permet de débloquer immédiatement le maillon le plus critique du projet.

---

## Proposed Solution

**Concept et approche.** Séparer strictement le **moteur linguistique** (texte → nombre) du **moteur vocal** (audio → texte), puis les chaîner :

```text
Audio → ASR (Omnilingual) → texte brut
Texte → normaliseur → parseur grammatical → nombre + confiance
```

Le cœur de la solution n'est pas l'IA vocale mais une **grammaire déterministe** du système numérique zarma, adossée à un **lexique versionné et validé par des locuteurs**. Le modèle vocal fournit une transcription ; la grammaire la valide, la corrige selon des variantes connues, et refuse d'inventer en cas d'ambiguïté.

**Différenciateurs clés.**
- **Pas de passage par le français** : moteur multilingue produisant directement du texte zarma.
- **Grammaire + lexique plutôt que table exhaustive** : un générateur `nombre → zarma` et un parseur `zarma → nombre` réversibles, testés par l'invariant `parse(generate(n)) == n` sur toute la plage.
- **Séparation variantes linguistiques vs erreurs ASR** : deux tables distinctes ; on ne « corrige » jamais aveuglément vers le mot le plus proche.
- **Prudence sur l'ambiguïté** : confiance composite (acoustique + grammaticale + variante connue + marge entre candidats + historique de confusions), et confirmation demandée plutôt que résultat forcé.
- **Architecture remplaçable** : interface ASR abstraite (`SpeechRecognizer`) permettant de changer de modèle (CTC, LLM, futur fine-tuné) sans réécrire l'application.

**Pourquoi ça réussira là où d'autres ont échoué.** Le succès dépend moins du volume de données que de quatre éléments maîtrisables dès le départ : une grammaire correcte, des transcriptions rigoureuses, un benchmark évalué par locuteur (jamais de fuite entre train et test), et une gestion prudente de l'ambiguïté. Le moteur linguistique est développable et entièrement testable **sans** modèle vocal installé, ce qui dérisque le projet et permet d'avancer même avant la résolution des ressources GPU.

**Vision produit.** Au-delà de la reconnaissance, l'architecture prépare une **réponse orale en zarma** (le générateur `nombre → zarma` existe déjà) et, à terme, un socle réutilisable (lexique, grammaire, corpus consenti) pour d'autres applications vocales zarma.

---

## Target Users

### Primary User Segment : Locuteur zarma utilisateur final

- **Profil.** Personnes parlant zarma en Afrique de l'Ouest, principalement au Niger (Niamey, Dosso et autres régions). Âges et niveaux d'alphabétisation variés. Équipés majoritairement de téléphones Android.
- **Comportements actuels.** Manipulent et prononcent des nombres oralement au quotidien (commerce, quantités, prix) mais n'ont aucun outil vocal numérique dans leur langue.
- **Besoins et douleurs.** Saisir/obtenir un nombre sans passer par une langue tierce ; un outil qui comprend leur prononciation naturelle, tolère les variantes régionales, et ne se trompe pas silencieusement.
- **Objectifs.** Dire un nombre et le voir correctement compris en chiffres, rapidement, avec possibilité de corriger simplement en cas d'erreur.

### Secondary User Segment : Contributeur / locuteur validateur

- **Profil.** Locuteurs natifs (3+ déjà accessibles pour la V1), idéalement de différentes tranches d'âge et régions (Niamey, Dosso, etc.), participant à la validation linguistique et à la collecte vocale consentie.
- **Comportements actuels.** Aucun cadre structuré pour contribuer à une ressource linguistique zarma.
- **Besoins et douleurs.** Un protocole clair et respectueux (consentement explicite, anonymat, possibilité de retrait) ; la certitude qu'aucune forme inventée n'est introduite dans le système.
- **Objectifs.** Faire reconnaître et pérenniser leur façon naturelle de dire les nombres ; contribuer à un patrimoine numérique zarma fiable.

---

## Goals & Success Metrics

### Business Objectives

- Livrer une bêta fonctionnelle Android où le parcours complet (enregistrer → reconnaître → confirmer/corriger) marche de bout en bout, évaluée sur des locuteurs non vus.
- Produire et publier un **lexique zarma numérique v1 validé** (`docs/numeration-zarma-v1.md` + `lexicon.yaml`), avec la forme du million résolue ou explicitement marquée bloquante.
- Établir un **moteur linguistique déterministe** passant l'invariant `parse(generate(n)) == n` sur toute la plage validée.
- Choisir le modèle ASR du MVP **à partir de données** (benchmark reproductible), pas d'une démonstration manuelle.
- Constituer un socle de données consenties et anonymisées réutilisable pour l'amélioration continue.

### User Success Metrics

- L'utilisateur obtient le bon nombre du premier coup dans la grande majorité des cas en environnement calme.
- Quand le système hésite, il demande confirmation au lieu de se tromper — l'utilisateur garde le contrôle.
- La correction d'un résultat est simple (clavier numérique + affichage automatique de la forme zarma canonique).
- Aucune fuite de données : l'audio ordinaire est supprimé après traitement, seul l'audio consenti est conservé.

### Key Performance Indicators (KPIs)

- **Exact Number Accuracy (métrique principale)** : nombres finaux corrects ÷ audios testés. Objectifs indicatifs de bêta (à ajuster après benchmark) : **≥ 95 %** (nouveaux locuteurs, calme), **≥ 90 %** (nouveaux locuteurs, bruit modéré).
- **Rejection Rate / False Acceptance Rate** : préférer rejeter/confirmer plutôt qu'accepter à tort ; le système ne doit jamais inventer un nombre sur une phrase non numérique.
- **Taux de confirmation & taux de correction** : suivis en production comme signaux de qualité et sources d'amélioration.
- **Latence totale et latence ASR** : mesurées séparément ; expérience réactive attendue.
- **Couverture linguistique** : nombre d'éléments du lexique avec statut `validé` vs `unresolved`.

---

## MVP Scope

### Core Features (Must Have)

- **Enregistrement audio contraint :** WAV PCM 16 bits, mono, 16 kHz, 1–8 s idéal / 10 s max, un seul locuteur, un seul nombre. Contrôles locaux (permission, durée min/max, taille, annulation, suppression du fichier temporaire).
- **Moteur linguistique zarma (le cœur) :** `lexicon.yaml` versionné + `normalizer.py` + `parser.py` + `generator.py` + `validator.py` + exceptions. Développé et testé **avant** l'interface mobile, indépendamment de FastAPI et de l'ASR.
- **Service ASR abstrait et remplaçable :** interface `SpeechRecognizer` avec implémentations CTC (`omniASR_CTC_300M_v2`, sans `lang`), LLM (`omniASR_LLM_300M_v2`, avec `lang=["dje_Latn"]`) et Mock. Service isolé de l'API.
- **API FastAPI :** endpoints `/health`, `/api/v1/models`, `/api/v1/grammar/version`, `/api/v1/recognize`, `/api/v1/feedback`, `/api/v1/recordings`, `/api/v1/history`. Réponse complète (nombre, texte normalisé, confiance, alternatives, versions modèle+grammaire). Validation Pydantic, timeout, rate limit, logs sans données sensibles.
- **Calcul de confiance composite et gestion de l'ambiguïté :** politique accepter / demander confirmation / demander répétition ; retour d'alternatives.
- **Application Flutter (Android) :** écrans Accueil, Enregistrement, Traitement, Résultat, Confirmation, Correction, Historique. Gestion complète des erreurs. Aucun secret embarqué.
- **Feedback et corrections utilisateur :** stockés pour métriques et amélioration.
- **Collecte vocale consentie (contribution) :** consentement explicite, prompts générés, métadonnées, upload, possibilité de retrait, validation avant intégration au dataset.
- **Persistance :** SQLite en dev / PostgreSQL en prod, migrations Alembic ; audio jamais stocké en base.

### Out of Scope for MVP

- Phrases longues, plusieurs nombres dans une même phrase.
- Opérations mathématiques, nombres décimaux, monnaies, dates, numéros de téléphone.
- Reconnaissance hors ligne sur le téléphone.
- Entraînement d'un modèle depuis zéro ; fine-tuning (déclenché seulement si nécessaire, après benchmark propre — Phase 9).
- Conversation générale en zarma.
- Réponse vocale en zarma (préparée par le générateur, mais livrée en Phase 10).
- **iOS** (repoussé post-MVP ; Android d'abord).

### MVP Success Criteria

Le MVP est considéré prêt pour une bêta lorsque : le système numérique zarma est validé et la forme du million résolue ; le moteur textuel passe tous ses tests (dont l'invariant exhaustif) ; le modèle ASR est choisi sur des données avec évaluation par locuteur non vu ; l'API retourne nombre + texte + confiance + versions ; l'application Android permet de confirmer et corriger ; les audios sont protégés (suppression par défaut, conservation sur consentement) ; le système préfère rejeter plutôt qu'inventer ; les métriques de production sont visibles.

---

## Post-MVP Vision

### Phase 2 Features

- **Réponse vocale en zarma** (Phase 10) : à partir du générateur `nombre → zarma` existant — audios préenregistrés assemblés (Option A), TTS adapté (Option B), ou réponse simple dans une langue déjà dotée d'une voix (Option C) en attendant une voix zarma fiable.
- **Support iOS.**
- **Amélioration du modèle** (Phase 9) uniquement si grammaire correcte + données propres + benchmark reproductible + modèle de base insuffisant : corpus élargi, décodage contraint, adaptation/fine-tuning comparé au modèle de base. Jamais d'entraînement depuis zéro.

### Long-term Vision

À un ou deux ans, disposer d'un socle vocal zarma réutilisable : lexique et grammaire numériques stables, corpus vocal consenti multi-régional, et pipeline d'amélioration continue alimenté par les corrections utilisateur. Le cas « nombres » sert de preuve et de fondation pour étendre la reconnaissance vocale zarma à d'autres domaines.

### Expansion Opportunities

- Élargissement du dataset (30–50 locuteurs, plusieurs téléphones, âges/régions variés) pour un modèle plus robuste.
- Extension à d'autres catégories linguistiques structurées (au-delà des nombres) réutilisant la même architecture séparée.
- Ouverture du lexique/grammaire comme ressource linguistique publique pour la communauté zarma.

---

## Technical Considerations

### Platform Requirements

- **Plateformes cibles :** Android en priorité pour le MVP (iOS post-MVP).
- **Support OS :** téléphones Android courants en Afrique de l'Ouest ; gestion robuste des permissions micro et des connexions lentes.
- **Performance :** enregistrement fiable ≤ 10 s ; latence totale maîtrisée ; indicateurs clairs en cas de réseau lent ; possibilité d'annuler la requête.

### Technology Preferences

- **Frontend :** Flutter. Packages `record`, `dio`, `path_provider`. Enregistrement WAV PCM 16 bits mono 16 kHz. Gestion d'état à trancher (Riverpod **ou** Bloc — une seule solution ; décision à l'étape architecture).
- **Backend :** Python 3.11, FastAPI, Pydantic, OpenAPI documenté.
- **Moteur linguistique :** paquet Python autonome `zarma_numbers` (indépendant de FastAPI et de l'ASR).
- **ASR :** Meta Omnilingual ASR (Apache 2.0), Python `>= 3.10, < 3.14`. Modèles CTC (rapides, sans conditionnement langue) et LLM (acceptent `dje_Latn`). Décision de modèle **après benchmark réel**.
- **Base de données :** SQLite (dev) → PostgreSQL (prod), migrations Alembic. Audio en stockage objet/répertoire sécurisé, jamais en base.
- **Hébergement/Infra :** Docker avec images séparées (API légère / ASR lourde), reverse proxy (nginx), HTTPS obligatoire, monitoring, sauvegardes. Environnements local / staging / production.

### Architecture Considerations

- **Structure de dépôt :** monorepo `zarma-numbers/` — `apps/mobile` (Flutter), `services/api` (FastAPI), `services/asr` (Omnilingual), `packages/zarma_numbers` (moteur linguistique), `dataset/`, `docs/`, `infrastructure/`, `scripts/`.
- **Architecture de services :** trois couches découplées — Flutter ↔ API FastAPI ↔ service ASR séparé ↔ normaliseur/parseur. Le moteur linguistique fonctionne sans ASR ; le service ASR se déploie et redémarre indépendamment de l'API.
- **Contraintes d'intégration :** `/api/v1/recognize` en `multipart/form-data` ; chaque reconnaissance conserve au minimum `model_version` et `grammar_version` ; contrôles serveur stricts sur l'audio (MIME réel, décodage, taille ≤ ~2 Mo, conversion mono 16 kHz, refus des fichiers corrompus, jamais d'exécution du fichier).
- **Sécurité/Conformité :** HTTPS ; identifiants anonymes ; aucune clé secrète dans Flutter ; `.env` hors Git ; rate limiting ; protection contre les fichiers malveillants ; suppression de l'audio par défaut, conservation uniquement sur consentement explicite ; anonymisation et retrait possible des contributions.

---

## Constraints & Assumptions

### Constraints

- **Budget :** non chiffré à ce stade. **Point ouvert critique :** aucune ressource GPU n'est encore allouée pour l'ASR (voir Risques). Un budget cloud GPU ou une machine GPU locale devra être décidé avant la Phase 4.
- **Timeline :** non datée ; séquencement par phases (0 → 10). Développeur solo à plein temps ⇒ phases essentiellement séquentielles, priorisation MVP stricte.
- **Ressources :** un seul développeur à plein temps. Machine de développement : MacBook Pro M1, 8 Go — suffisant pour Flutter, FastAPI, le parseur, les tests, la base locale et la préparation du dataset, **mais pas** pour servir le modèle ASR de production. 3+ locuteurs natifs zarma accessibles pour la validation linguistique.
- **Technique :** le Mac M1 8 Go ne peut pas héberger l'ASR de production (chiffres mémoire mesurés sur GPU A100, pas sur Mac). Les modèles CTC n'acceptent pas `lang=["dje_Latn"]` ; seuls les modèles LLM acceptent le conditionnement. Audio ≤ 10 s côté application.

### Key Assumptions

- Omnilingual ASR fournit une transcription zarma exploitable après normalisation — **à confirmer par benchmark**, la métrique de décision étant l'Exact Number Accuracy (et non le WER).
- La grammaire numérique zarma est régulière et suffisamment déterministe pour couvrir `0`–`1 000 000` avec un lexique compact — sous réserve de validation par locuteurs.
- Les 3+ locuteurs disponibles permettent d'atteindre au moins la règle de décision (unanimité / majorité 2 sur 3) sur les formes clés, y compris 10 000, 100 000 et 1 000 000.
- Le moteur linguistique peut être entièrement développé et validé avant toute installation de modèle vocal.
- L'invariant `parse(generate(n)) == n` est atteignable sur toute la plage une fois la grammaire gelée.
- Une ressource GPU (cloud ou locale) sera obtenue avant la Phase 4.

---

## Risks & Open Questions

### Key Risks

- **Ressource ASR non résolue (élevé, n°1) :** aucune machine GPU allouée. Le benchmark ASR (Phase 4) et la reconnaissance de production sont bloqués tant que ce point n'est pas tranché. *Mitigation :* avancer entièrement Phases 0–3 (moteur linguistique + corpus) qui n'exigent pas de GPU, en parallèle décider budget cloud GPU vs machine locale, et utiliser le `MockRecognizer` pour développer l'API et Flutter sans ASR réel.
- **Forme du million non résolue (moyen-élevé) :** `1 000 000` est marqué `unresolved` dans la spec, ainsi que 10 000 et 100 000. Bloque le gel de la grammaire et l'invariant exhaustif. *Mitigation :* prioriser ces formes lors de la validation linguistique avec les locuteurs disponibles ; marquer explicitement bloquant si non résolu.
- **Qualité/représentativité linguistique (moyen) :** 3 locuteurs suffisent pour démarrer mais pas pour couvrir les variantes régionales ; risque de figer une forme non représentative. *Mitigation :* respecter la règle de décision (unanimité/majorité), conserver les variantes reconnues, viser ensuite 5–10 locuteurs de régions différentes, ne jamais inventer ni supprimer une variante correcte.
- **Confusions acoustiques graves (moyen) :** paires proches (hinka/hinza, iyye/yega…) où une erreur d'une lettre change le nombre. *Mitigation :* pas de fuzzy matching décisionnel ; table de confusions ASR séparée ; confiance composite ; confirmation en cas d'ambiguïté.
- **Charge solo (moyen) :** un seul développeur sur un périmètre large (linguistique + backend + ASR + mobile + infra + collecte). *Mitigation :* séquencement strict par phases, MVP minimaliste, tests écrits en même temps que le code.
- **Généralisation aux nouveaux locuteurs (moyen) :** un modèle performant sur locuteurs connus peut chuter sur des voix inédites. *Mitigation :* séparation des données **par locuteur** (aucune voix de test dans l'entraînement) ; objectifs mesurés sur locuteurs non vus.

### Open Questions

- Ressource GPU pour l'ASR : cloud (quel fournisseur/budget) ou machine locale ? Quand ?
- Formes canoniques exactes de 10 000, 100 000 et 1 000 000 ? (`zambar yagga` / `miliyo` / autre ?)
- Résolution des incohérences orthographiques : `iddou`/`iddu`, `iyega`/`yega`/`yegga`, `ahakou`/`hakou`/`hakkou`, `nda`/`da`, `zangou`/`zangu`, forme de `iwey`, usage de `fo` après `zambar` pour 1 000, comportement des voyelles initiales en formes combinées.
- Gestion d'état Flutter : Riverpod ou Bloc ? (à trancher à l'étape architecture)
- Cible iOS : confirmée post-MVP, mais à quelle échéance ?
- Modèle ASR retenu pour le MVP (CTC 300M vs LLM 300M) : dépend du benchmark.
- Politique de conservation/retrait des données et contenu exact du consentement (versionné).

### Areas Needing Further Research

- Benchmark ASR reproductible : ≥ 100 audios, plusieurs locuteurs, nombres courts/longs et paires proches, jeu de test par locuteur, comparaison CTC vs LLM sur Exact Number Accuracy, matrice de confusions.
- Options de déploiement GPU (coût, latence, disponibilité) pour le service ASR.
- Faisabilité et prosodie de la réponse vocale zarma (audios préenregistrés vs TTS adapté) — Phase 10.
- Calibration des poids et seuils du score de confiance composite à partir de données réelles.

---

## Appendices

### A. Research Summary

Ce brief est dérivé d'un document de cadrage exhaustif (`docs/specification-complete-application-nombres-zarma.md`, v1.0, 23 juillet 2026) couvrant : périmètre MVP, décisions techniques (séparation moteur linguistique / moteur vocal, pas de transcription française, pas de table exhaustive), spécification linguistique provisoire (unités, dizaines, échelles, connecteurs, exemples 0–999 999), protocole de validation linguistique, lexique versionné, normalisation, grammaire (pseudo-EBNF), générateur, stratégie et benchmark ASR, calcul de confiance, traitement audio, API FastAPI, schéma de base de données, écrans Flutter, collecte de données, protection des données/consentement, tests, critères d'acceptation, déploiement, CI/CD, et feuille de route en 11 phases (0–10).

Points vérifiés notables : Omnilingual ASR supporte `dje_Latn` (Apache 2.0) ; modèles CTC sans conditionnement langue, modèles LLM avec `lang=["dje_Latn"]` ; pipeline audio mono 16 kHz.

### B. Stakeholder Input

Décisions de cadrage confirmées par le porteur du projet (23/07/2026) :
- 3+ locuteurs natifs zarma accessibles immédiatement pour la validation linguistique.
- Aucune ressource GPU encore allouée pour l'ASR (décision à prendre) — identifié comme risque n°1.
- Développeur solo à plein temps.
- Android prioritaire pour le MVP, iOS post-MVP.

### C. References

- Spécification complète : `docs/specification-complete-application-nombres-zarma.md`
- Meta Omnilingual ASR : https://github.com/facebookresearch/omnilingual-asr
- Guide d'inférence : https://github.com/facebookresearch/omnilingual-asr/blob/main/src/omnilingual_asr/models/inference/README.md
- Codes de langue : https://github.com/facebookresearch/omnilingual-asr/blob/main/src/omnilingual_asr/models/wav2vec2_llama/lang_ids.py
- Enregistrement audio Flutter : https://docs.flutter.dev/cookbook/audio/record
- Fichiers envoyés FastAPI : https://fastapi.tiangolo.com/tutorial/request-files/

---

## Next Steps

### Immediate Actions

1. **Trancher la ressource GPU ASR** (cloud vs local) — débloque la Phase 4 ; à faire en parallèle des phases sans GPU.
2. Créer le dépôt monorepo et les dossiers ; initialiser Git, `.gitignore`, `.env.example` (Phase 0).
3. Créer `docs/numeration-zarma-v1.md` et lancer la validation avec les 3+ locuteurs disponibles (Phase 1), en **priorisant** 10 000, 100 000 et 1 000 000.
4. Geler le lexique v1 (`lexicon.yaml`) une fois les formes validées.
5. Développer le moteur textuel — `normalizer.py`, `parser.py`, `generator.py` — avec tests, jusqu'à `parse(generate(n)) == n` sur toute la plage (Phase 2).
6. Constituer le corpus de benchmark (≥ 100 audios, plusieurs locuteurs, split par locuteur) (Phase 3).
7. Seulement ensuite : benchmarker Omnilingual ASR (CTC vs LLM) et choisir le modèle sur l'Exact Number Accuracy (Phase 4).

### PM Handoff

This Project Brief provides the full context for **Zarma — Reconnaissance des nombres prononcés en zarma**. Please start in 'PRD Generation Mode', review the brief thoroughly to work with the user to create the PRD section by section as the template indicates, asking for any necessary clarification or suggesting improvements.

Recommandation de séquence BMAD : `/pm` (PRD) → `/architect` (architecture, avec décision Riverpod vs Bloc et déploiement ASR) → `/po` → `/sm` → `/dev` → `/qa`.