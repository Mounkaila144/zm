# Zarma — Reconnaissance des nombres prononcés en zarma — Product Requirements Document (PRD)

**Version :** 1.0
**Date :** 23 juillet 2026
**Auteur :** John (Product Manager, BMAD)
**Source principale :** `docs/brief.md`, `docs/specification-complete-application-nombres-zarma.md`
**Statut :** Brouillon pour revue (généré en mode YOLO)

---

## Goals and Background Context

### Goals

- Livrer une bêta Android où le parcours complet **enregistrer → reconnaître → confirmer/corriger** fonctionne de bout en bout, évaluée sur des locuteurs non vus.
- Fournir un **moteur linguistique déterministe** zarma (texte ↔ nombre) passant l'invariant `parse(generate(n)) == n` sur toute la plage `0`–`1 000 000`.
- Publier un **lexique numérique zarma v1 validé** par des locuteurs natifs, avec les formes de 10 000 / 100 000 / 1 000 000 résolues ou explicitement marquées bloquantes.
- Choisir le **modèle ASR du MVP sur des données** (benchmark reproductible, métrique Exact Number Accuracy), et jamais sur une démonstration manuelle.
- Garantir un système **prudent** qui préfère demander confirmation ou rejeter plutôt qu'inventer un nombre, sans jamais passer par le français.
- Constituer un **socle de données consenties et anonymisées** réutilisable pour l'amélioration continue et de futures applications vocales zarma.

### Background Context

Le zarma (`dje_Latn`), parlé par plusieurs millions de personnes en Afrique de l'Ouest (principalement au Niger), est quasi absent des technologies vocales. Les moteurs grand public ne le supportent pas directement et le font transiter par le français, ce qui confond des formes acoustiquement proches mais numériquement très différentes (`hinka`/`hinza`, `iyye`/`yega`, `iddu`/`iyye`) et produit des erreurs graves et silencieuses. Pour une langue à forte tradition orale, saisir un nombre par la voix est un cas d'usage à forte valeur (commerce, comptage, éducation, accessibilité) et un point d'entrée réaliste pour bâtir un écosystème vocal zarma.

La publication récente de Meta Omnilingual ASR (Apache 2.0), qui annonce le support de `dje_Latn`, ouvre une fenêtre d'opportunité : construire un moteur zarma sérieux sans entraîner de modèle depuis zéro. L'approche retenue sépare strictement le **moteur linguistique** (texte → nombre, déterministe, testable sans GPU) du **moteur vocal** (audio → texte, remplaçable), et s'appuie sur une grammaire formalisée, un lexique versionné validé par des locuteurs, une table de corrections ASR distincte des variantes linguistiques, et une gestion prudente de l'ambiguïté. Le maillon critique — la validation linguistique — est débloquable immédiatement grâce à 3+ locuteurs natifs disponibles.

### Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-07-23 | 1.0 | Création initiale du PRD à partir du brief (mode YOLO) | John (PM) |

---

## Requirements

### Functional

- **FR1 :** Le système enregistre un audio contraint au format WAV PCM 16 bits, mono, 16 kHz, d'une durée idéale de 1 à 8 s (10 s maximum), pour un seul locuteur prononçant un seul nombre entier.
- **FR2 :** L'application applique des contrôles locaux d'enregistrement : demande de permission micro, bornes de durée min/max, contrôle de taille, annulation en cours, et suppression du fichier temporaire après traitement.
- **FR3 :** Le moteur linguistique génère la forme zarma canonique d'un nombre entier (`generate(n)`) sur la plage `0`–`1 000 000`.
- **FR4 :** Le moteur linguistique analyse un texte zarma normalisé et retourne le nombre entier correspondant (`parse(texte)`), ou une absence de résultat si le texte n'est pas un nombre valide.
- **FR5 :** Le système normalise le texte brut issu de l'ASR (casse, orthographes alternatives connues, connecteurs, espaces) avant analyse grammaticale.
- **FR6 :** Le moteur linguistique satisfait l'invariant `parse(generate(n)) == n` sur toute la plage `0`–`1 000 000` une fois la grammaire gelée.
- **FR7 :** Le lexique est versionné et chaque élément porte un statut (`validé` ou `unresolved`), la version du lexique/grammaire étant exposée par le système.
- **FR8 :** Le système maintient deux tables distinctes — variantes linguistiques reconnues d'une part, corrections d'erreurs ASR d'autre part — et ne corrige jamais aveuglément un mot vers le plus proche.
- **FR9 :** Le service de reconnaissance vocale expose une interface abstraite `SpeechRecognizer` avec au moins trois implémentations : CTC (`omniASR_CTC_300M_v2`, sans `lang`), LLM (`omniASR_LLM_300M_v2`, avec `lang=["dje_Latn"]`) et Mock.
- **FR10 :** L'endpoint `/api/v1/recognize` (multipart/form-data) retourne le nombre compris, le texte zarma normalisé, un score de confiance, une liste d'alternatives candidates, ainsi que `model_version` et `grammar_version`.
- **FR11 :** L'API expose les endpoints `/health`, `/api/v1/models`, `/api/v1/grammar/version`, `/api/v1/recognize`, `/api/v1/feedback`, `/api/v1/recordings`, `/api/v1/history`.
- **FR12 :** Le système calcule un score de confiance composite intégrant les signaux acoustique, grammatical, variante connue, marge entre candidats, et historique de confusions.
- **FR13 :** Selon la confiance, le système applique une politique explicite : **accepter**, **demander confirmation**, ou **demander répétition**.
- **FR14 :** L'application Flutter fournit les écrans Accueil, Enregistrement, Traitement, Résultat, Confirmation, Correction et Historique, avec gestion complète des erreurs.
- **FR15 :** En cas d'ambiguïté, le système demande confirmation à l'utilisateur en présentant le(s) candidat(s) plutôt que de forcer un résultat.
- **FR16 :** L'utilisateur peut corriger un résultat via un clavier numérique, l'application affichant automatiquement la forme zarma canonique correspondant au nombre corrigé.
- **FR17 :** Le système conserve et affiche un historique des reconnaissances de l'utilisateur.
- **FR18 :** Les feedbacks et corrections utilisateur sont stockés pour alimenter les métriques et l'amélioration continue.
- **FR19 :** La collecte vocale consentie couvre : consentement explicite (versionné), génération de prompts, métadonnées, upload, possibilité de retrait, et validation avant intégration au dataset.
- **FR20 :** L'audio ordinaire est supprimé après traitement par défaut ; seul l'audio explicitement consenti est conservé.
- **FR21 :** Le système ne doit jamais inventer un nombre à partir d'une phrase non numérique : il rejette ou demande une répétition.
- **FR22 :** La persistance utilise SQLite en développement et PostgreSQL en production avec migrations Alembic ; l'audio n'est jamais stocké en base (stockage objet/répertoire sécurisé).
- **FR23 :** Chaque réponse de reconnaissance ambiguë inclut les alternatives candidates ordonnées pour permettre la confirmation.

### Non Functional

- **NFR1 :** L'expérience est réactive ; la latence totale et la latence ASR sont mesurées séparément et exposées comme signaux de qualité.
- **NFR2 :** Objectif de qualité (Exact Number Accuracy, à ajuster après benchmark) : **≥ 95 %** sur nouveaux locuteurs en environnement calme, **≥ 90 %** sur nouveaux locuteurs en bruit modéré.
- **NFR3 :** Sécurité : HTTPS obligatoire, aucun secret ou clé embarqué dans Flutter, fichiers `.env` hors Git.
- **NFR4 :** L'API applique un rate limiting et des timeouts sur les endpoints sensibles.
- **NFR5 :** Contrôles serveur stricts sur l'audio : vérification du MIME réel, décodage, taille ≤ ~2 Mo, conversion mono 16 kHz, refus des fichiers corrompus, aucune exécution du fichier.
- **NFR6 :** Les logs ne contiennent aucune donnée sensible ni identifiante.
- **NFR7 :** Les contributions utilisent des identifiants anonymes ; l'anonymisation et le retrait des contributions sont possibles.
- **NFR8 :** Le moteur linguistique est entièrement développable et testable **sans** modèle ASR installé, indépendamment de FastAPI.
- **NFR9 :** L'architecture ASR est remplaçable : changer de modèle (CTC, LLM, futur fine-tuné) ne doit pas nécessiter de réécrire l'application ni l'API.
- **NFR10 :** Les jeux de données sont séparés **par locuteur** : aucune voix présente dans le jeu de test ne figure dans l'entraînement/la calibration.
- **NFR11 :** L'application fonctionne sur les téléphones Android courants en Afrique de l'Ouest et gère robustement les permissions micro et les connexions lentes (indicateurs clairs, annulation possible).
- **NFR12 :** Chaque reconnaissance persistée conserve au minimum `model_version` et `grammar_version` pour la traçabilité et la reproductibilité.
- **NFR13 :** Le déploiement s'appuie sur Docker avec images séparées (API légère / ASR lourde), reverse proxy nginx, monitoring, sauvegardes, et environnements local / staging / production distincts.
- **NFR14 :** Aucun fuzzy matching décisionnel (ex. distance de Levenshtein aveugle) n'est utilisé pour trancher un nombre.
- **NFR15 :** Contraintes de runtime : backend Python 3.11 (FastAPI, Pydantic) ; service ASR compatible Python `>= 3.10, < 3.14`.

---

## User Interface Design Goals

### Overall UX Vision

Une application **minimaliste, orale-first et rassurante**, conçue pour des utilisateurs aux niveaux d'alphabétisation variés. Le geste central est unique et évident : appuyer sur un gros bouton micro, parler, obtenir un nombre. L'UX privilégie la **confiance et le contrôle** : le système montre clairement ce qu'il a compris, demande confirmation quand il hésite, et rend la correction triviale. Aucun jargon technique n'est exposé à l'utilisateur final ; les scores et versions restent en coulisses (utiles au diagnostic, pas à l'écran principal).

### Key Interaction Paradigms

- **Un seul geste principal** : bouton micro proéminent (press-to-record ou tap-to-start/stop) avec retour visuel d'enregistrement (niveau audio, minuterie, limite 10 s).
- **Boucle de confirmation** : Résultat → soit accepté immédiatement (haute confiance), soit écran de confirmation présentant le(s) candidat(s), soit invitation à répéter.
- **Correction directe** : clavier numérique pour saisir le bon nombre, avec affichage immédiat de la forme zarma canonique (renforce l'apprentissage et la confiance).
- **Feedback non intrusif** : indicateurs d'état clairs (enregistrement, traitement, réseau lent, erreur) via icônes et couleurs plutôt que texte dense.

### Core Screens and Views

- **Écran Accueil** (point d'entrée, bouton micro, accès historique)
- **Écran Enregistrement** (retour audio, minuterie, annulation)
- **Écran Traitement** (état de la reconnaissance, annulation possible)
- **Écran Résultat** (nombre en chiffres + forme zarma)
- **Écran Confirmation** (candidats en cas d'ambiguïté)
- **Écran Correction** (clavier numérique + forme zarma canonique)
- **Écran Historique** (reconnaissances passées)
- **Écran/Flux Contribution & Consentement** (collecte vocale consentie, prompts, retrait)

### Accessibility: WCAG AA

Cible **WCAG AA** adaptée au mobile : contrastes suffisants, cibles tactiles larges, dépendance minimale au texte (icônes + couleurs + éventuels repères audio), compatibilité lecteurs d'écran Android. Pertinent pour une audience à alphabétisation variable.

### Branding

Aucune charte graphique imposée à ce stade. Recommandation : identité sobre et culturellement respectueuse, valorisant la langue zarma (affichage systématique de la forme zarma à côté des chiffres). À préciser avec l'UX Expert.

### Target Device and Platforms: Mobile Only (Android d'abord)

**Android en priorité** pour le MVP (téléphones courants d'Afrique de l'Ouest). iOS repoussé post-MVP. Pas de version web ni desktop dans le périmètre MVP.

---

## Technical Assumptions

### Repository Structure: Monorepo

Monorepo `zarma-numbers/` regroupant : `apps/mobile` (Flutter), `services/api` (FastAPI), `services/asr` (Omnilingual), `packages/zarma_numbers` (moteur linguistique), `dataset/`, `docs/`, `infrastructure/`, `scripts/`. Justification : cohérence des versions (grammaire/lexique), partage de contrats API, développeur solo, et découplage logique via des paquets/services séparés au sein d'un seul dépôt.

### Service Architecture

**Trois couches découplées au sein du monorepo** : Flutter ↔ API FastAPI ↔ service ASR séparé, le tout s'appuyant sur le paquet moteur linguistique. Justification : le service ASR (lourd, GPU) se déploie et redémarre indépendamment de l'API (légère) ; le moteur linguistique fonctionne sans ASR ; l'interface `SpeechRecognizer` rend le modèle vocal remplaçable. Ce n'est pas du microservices « distribué » complet, mais une séparation nette des responsabilités et des cycles de déploiement.

### Testing Requirements

**Unit + Integration**, avec exigence spéciale sur le moteur linguistique. Justification :
- Moteur linguistique : tests unitaires exhaustifs, dont l'**invariant `parse(generate(n)) == n` sur toute la plage** `0`–`1 000 000`, tests de normalisation et de variantes.
- API : tests d'intégration des endpoints avec `MockRecognizer` (aucun GPU requis), validation des schémas Pydantic, gestion d'erreurs, rate limiting.
- Benchmark ASR : évaluation reproductible sur jeu de test **séparé par locuteur** (métrique Exact Number Accuracy, matrice de confusions) — traité comme harnais d'évaluation, pas comme test unitaire.
- Mobile : tests des widgets/écrans clés et du flux de correction ; tests manuels de convenance sur device réel pour l'audio.

### Additional Technical Assumptions and Requests

- **Frontend :** Flutter ; packages `record`, `dio`, `path_provider` ; enregistrement WAV PCM 16 bits mono 16 kHz. **Gestion d'état (Riverpod vs Bloc) à trancher par l'Architect** — une seule solution retenue.
- **Backend :** Python 3.11, FastAPI, Pydantic, OpenAPI documenté.
- **Moteur linguistique :** paquet Python autonome `zarma_numbers` indépendant de FastAPI et de l'ASR (`lexicon.yaml`, `normalizer.py`, `parser.py`, `generator.py`, `validator.py`, exceptions).
- **ASR :** Meta Omnilingual ASR (Apache 2.0). Modèles CTC (rapides, sans conditionnement langue) et LLM (acceptent `lang=["dje_Latn"]`). **Décision de modèle après benchmark réel** sur Exact Number Accuracy, pas WER.
- **Base de données :** SQLite (dev) → PostgreSQL (prod), migrations Alembic ; audio jamais en base.
- **Infra/Déploiement :** Docker (images API légère / ASR lourde séparées), nginx, HTTPS obligatoire, monitoring, sauvegardes ; environnements local / staging / production.
- **Ressource GPU ASR — DÉCISION OUVERTE (risque n°1) :** aucune machine GPU n'est allouée. Le benchmark (et la reconnaissance de production) est bloqué tant que cloud vs local n'est pas tranché. Mitigation : développer entièrement le moteur linguistique, l'API (via `MockRecognizer`) et le mobile sans GPU. Le Mac M1 8 Go ne peut pas servir l'ASR de production.
- **Formes canoniques 10 000 / 100 000 / 1 000 000 — OUVERTES :** marquées `unresolved` ; à résoudre en priorité lors de la validation linguistique, sinon marquées explicitement bloquantes.
- **Contrats d'intégration :** `/api/v1/recognize` en `multipart/form-data` ; conservation systématique de `model_version` + `grammar_version`.

---

## Epic List

- **Epic 1 — Fondations & Moteur linguistique déterministe :** établir le monorepo, l'outillage (Git, CI, lint, tests), valider et geler le lexique numérique zarma v1, et livrer le paquet `zarma_numbers` (générateur, normaliseur, parseur, validateur) passant l'invariant exhaustif — un moteur texte↔nombre entièrement testable, sans GPU ni mobile.
- **Epic 2 — API de reconnaissance & Service ASR remplaçable :** exposer l'API FastAPI (health, models, grammar/version, recognize, feedback, recordings, history) branchée sur le moteur linguistique via un `SpeechRecognizer` abstrait (Mock + CTC + LLM), avec confiance composite, politique d'ambiguïté, persistance et sécurité — un parcours de reconnaissance de bout en bout démontrable avec `MockRecognizer`.
- **Epic 3 — Application mobile Android (parcours complet) :** livrer l'app Flutter (enregistrement contraint, traitement, résultat, confirmation, correction, historique) connectée à l'API, avec gestion des erreurs et des réseaux lents — le parcours utilisateur complet enregistrer → reconnaître → confirmer/corriger.
- **Epic 4 — Collecte consentie, feedback & socle de données :** implémenter le consentement versionné, la génération de prompts, l'upload et le retrait des contributions, la validation avant intégration au dataset, et le stockage des corrections/feedbacks pour les métriques — le socle de données consenties et anonymisées.
- **Epic 5 — Benchmark ASR, sélection du modèle & calibration :** constituer le corpus de benchmark (≥ 100 audios, split par locuteur), comparer CTC vs LLM sur l'Exact Number Accuracy, produire la matrice de confusions, sélectionner le modèle du MVP et calibrer les poids/seuils de la confiance composite — la décision ASR fondée sur les données et la qualité de bêta mesurée.

---

## Epic 1 — Fondations & Moteur linguistique déterministe

**Objectif étendu :** établir toute la fondation projet (monorepo, gestion de version, CI, qualité de code) et livrer le cœur du produit : un moteur linguistique zarma déterministe et réversible, adossé à un lexique v1 validé par des locuteurs natifs. À la fin de cet epic, on dispose d'un paquet Python autonome capable de convertir nombre ↔ zarma sur `0`–`1 000 000`, prouvé par l'invariant `parse(generate(n)) == n`, sans dépendre d'un GPU, de l'ASR, de l'API ou du mobile — ce qui dérisque immédiatement le projet.

### Story 1.1 — Initialisation du monorepo et de l'outillage

En tant que développeur,
je veux un monorepo initialisé avec la structure de dossiers, le contrôle de version et l'outillage qualité,
afin de disposer d'une base saine et cohérente pour toutes les couches du projet.

#### Acceptance Criteria

1. Le dépôt contient la structure `apps/mobile`, `services/api`, `services/asr`, `packages/zarma_numbers`, `dataset/`, `docs/`, `infrastructure/`, `scripts/`.
2. Git est initialisé avec `.gitignore` approprié (Python, Flutter, `.env`, artefacts) et `.env.example` fourni ; aucun secret n'est committé.
3. L'outillage qualité Python (formatteur, linter, exécuteur de tests) est configuré et exécutable localement.
4. Une pipeline CI exécute lint + tests du paquet `zarma_numbers` à chaque push.
5. Un README racine décrit la structure du monorepo et les commandes de base.

### Story 1.2 — Spécification et validation du système numérique zarma v1

En tant que responsable produit,
je veux formaliser le système numérique zarma et le faire valider par des locuteurs natifs,
afin de figer des formes canoniques fiables avant de coder la grammaire.

#### Acceptance Criteria

1. `docs/numeration-zarma-v1.md` documente unités, dizaines, échelles, connecteurs et exemples couvrant `0`–`999 999`.
2. Un protocole de validation est appliqué avec au moins 3 locuteurs natifs selon une règle de décision explicite (unanimité / majorité 2 sur 3).
3. Les formes de **10 000, 100 000 et 1 000 000** sont traitées en priorité et chacune est soit résolue (forme canonique retenue), soit explicitement marquée bloquante.
4. Les variantes régionales/orthographiques reconnues (`iddou`/`iddu`, `iyega`/`yega`, `zangou`/`zangu`, `nda`/`da`, etc.) sont recensées et conservées, jamais inventées ni supprimées arbitrairement.
5. Le document indique clairement le statut de chaque forme (`validé` / `unresolved`) et la règle de décision utilisée.

### Story 1.3 — Lexique versionné `lexicon.yaml`

En tant que développeur,
je veux un lexique numérique zarma versionné et chargeable,
afin que la grammaire s'appuie sur une source de vérité unique et traçable.

#### Acceptance Criteria

1. `lexicon.yaml` encode unités, dizaines, échelles, connecteurs et variantes, chaque entrée portant un statut (`validé` / `unresolved`).
2. Le lexique porte un numéro de version (`grammar_version`) exposable par le code.
3. Un chargeur valide la structure du lexique au démarrage et échoue proprement si une entrée requise est manquante ou incohérente.
4. Les variantes linguistiques et les corrections d'erreurs ASR sont stockées dans **deux structures distinctes**.
5. Des tests vérifient le chargement, le versionnage et la séparation variantes vs corrections ASR.

### Story 1.4 — Générateur `nombre → zarma`

En tant qu'utilisateur du moteur,
je veux obtenir la forme zarma canonique d'un nombre,
afin d'afficher la prononciation correcte et de préparer la future réponse orale.

#### Acceptance Criteria

1. `generator.py` produit la forme zarma canonique pour tout entier de `0` à `1 000 000` (dans les limites des formes validées).
2. Les connecteurs et règles de composition suivent la grammaire documentée en 1.2.
3. Les nombres hors plage ou invalides sont refusés avec une erreur explicite.
4. Des tests couvrent des cas représentatifs (unités, dizaines, centaines, milliers, échelles, cas limites `0`, `10 000`, `100 000`, `1 000 000`).

### Story 1.5 — Normaliseur de texte

En tant que développeur,
je veux normaliser un texte zarma brut avant analyse,
afin d'absorber les variations d'orthographe et de casse sans corrompre le sens numérique.

#### Acceptance Criteria

1. `normalizer.py` normalise casse, espaces, connecteurs et orthographes alternatives connues vers des formes canoniques.
2. La normalisation s'appuie sur la table de variantes linguistiques (jamais sur du fuzzy matching décisionnel).
3. La normalisation est idempotente (`normalize(normalize(x)) == normalize(x)`).
4. Des tests couvrent variantes orthographiques, connecteurs et entrées non numériques.

### Story 1.6 — Parseur `zarma → nombre` et invariant exhaustif

En tant qu'utilisateur du moteur,
je veux convertir un texte zarma en nombre de façon fiable et prouvée,
afin de garantir l'exactitude du cœur du produit indépendamment de l'ASR.

#### Acceptance Criteria

1. `parser.py` analyse un texte zarma normalisé et retourne l'entier correspondant, ou une absence de résultat explicite si le texte n'est pas un nombre valide.
2. Le parseur ne devine ni n'invente jamais un nombre à partir d'un texte non numérique (retour vide/erreur, jamais une valeur arbitraire).
3. `validator.py` exécute l'invariant `parse(generate(n)) == n` sur **toute la plage** `0`–`1 000 000` et le test passe (sur les formes validées ; les formes `unresolved` sont explicitement tracées).
4. La couverture inclut les paires de confusion connues (`hinka`/`hinza`, `iyye`/`yega`, `iddu`/`iyye`) traitées comme distinctes.
5. La CI exécute l'invariant et échoue si une forme validée le viole.

---

## Epic 2 — API de reconnaissance & Service ASR remplaçable

**Objectif étendu :** exposer le moteur linguistique via une API FastAPI robuste et sécurisée, avec une couche ASR abstraite et remplaçable. À la fin de cet epic, un client peut envoyer un audio et recevoir nombre + texte normalisé + confiance + alternatives + versions, avec une politique d'ambiguïté prudente, une persistance conforme (audio hors base) et une sécurité de base — le tout démontrable de bout en bout avec `MockRecognizer`, sans GPU.

### Story 2.1 — Squelette API FastAPI, `/health` et versions

En tant que développeur,
je veux une API FastAPI démarrable exposant santé et versions,
afin d'établir la couche service et sa traçabilité dès le départ.

#### Acceptance Criteria

1. `services/api` démarre via FastAPI et expose `/health` retournant un statut OK.
2. `/api/v1/grammar/version` retourne la `grammar_version` issue du lexique, et `/api/v1/models` liste les recognizers disponibles.
3. La documentation OpenAPI est générée et accessible.
4. La configuration provient de variables d'environnement (`.env` hors Git) ; aucun secret n'est en dur.
5. Des tests d'intégration couvrent `/health`, `/models`, `/grammar/version`.

### Story 2.2 — Interface `SpeechRecognizer` et `MockRecognizer`

En tant qu'architecte,
je veux une abstraction de reconnaissance vocale avec une implémentation Mock,
afin de développer et tester l'API sans dépendre d'un GPU ni d'un modèle réel.

#### Acceptance Criteria

1. Une interface `SpeechRecognizer` définit un contrat clair (audio → texte + signaux acoustiques/métadonnées).
2. `MockRecognizer` retourne des transcriptions déterministes configurables pour les tests.
3. Le service ASR est isolé de l'API (paquet/module séparé), sélectionnable par configuration.
4. Des tests valident le contrat de l'interface et le comportement du Mock.

### Story 2.3 — Endpoint `/recognize` (pipeline complet via Mock)

En tant qu'utilisateur,
je veux envoyer un audio et recevoir le nombre compris,
afin d'obtenir le résultat de reconnaissance de bout en bout.

#### Acceptance Criteria

1. `/api/v1/recognize` accepte du `multipart/form-data` (fichier audio) et enchaîne ASR → normalisation → parsing.
2. La réponse contient : nombre, texte normalisé, score de confiance, alternatives, `model_version`, `grammar_version`.
3. La validation d'entrée est faite par Pydantic ; les entrées invalides renvoient des erreurs claires.
4. Un timeout est appliqué et les erreurs internes ne fuient aucune donnée sensible.
5. Des tests d'intégration couvrent le pipeline avec `MockRecognizer` (cas nombre valide, texte non numérique rejeté, audio invalide).

### Story 2.4 — Validation et traitement sécurisés de l'audio

En tant que responsable sécurité,
je veux des contrôles serveur stricts sur l'audio reçu,
afin d'éviter les fichiers malveillants et de garantir un format exploitable.

#### Acceptance Criteria

1. Le serveur vérifie le MIME réel, décode l'audio, et refuse les fichiers corrompus ou trop volumineux (≤ ~2 Mo).
2. L'audio est converti/normalisé en mono 16 kHz avant traitement.
3. Le fichier audio n'est jamais exécuté et est traité dans un contexte isolé.
4. Par défaut, l'audio ordinaire est supprimé après traitement (aucune conservation sans consentement).
5. Des tests couvrent un fichier valide, un fichier corrompu, un fichier trop gros et un MIME incohérent.

### Story 2.5 — Confiance composite et politique d'ambiguïté

En tant qu'utilisateur,
je veux que le système hésite plutôt que de se tromper,
afin de garder le contrôle et d'éviter les erreurs numériques silencieuses.

#### Acceptance Criteria

1. Un score de confiance composite combine signaux acoustique, grammatical, variante connue, marge entre candidats et historique de confusions.
2. La politique produit une décision explicite : accepter / demander confirmation / demander répétition.
3. En cas d'ambiguïté, la réponse inclut les alternatives candidates ordonnées.
4. Le système ne retourne jamais un nombre pour une phrase non numérique (rejet ou répétition).
5. Les poids/seuils sont configurables (valeurs par défaut documentées ; calibration réelle en Epic 5).
6. Des tests couvrent haute confiance, ambiguïté (deux candidats proches) et rejet.

### Story 2.6 — Persistance, historique et feedback

En tant que responsable produit,
je veux persister reconnaissances, historique et feedbacks,
afin de suivre la qualité et d'alimenter l'amélioration continue.

#### Acceptance Criteria

1. La base est SQLite en dev et PostgreSQL en prod, avec migrations Alembic ; l'audio n'est jamais stocké en base.
2. Chaque reconnaissance persistée conserve au minimum `model_version` et `grammar_version`.
3. `/api/v1/history` retourne l'historique des reconnaissances d'un identifiant anonyme.
4. `/api/v1/feedback` enregistre les corrections/feedbacks utilisateur.
5. Les logs ne contiennent aucune donnée sensible ; des tests couvrent l'écriture et la relecture de l'historique et du feedback.

### Story 2.7 — Rate limiting et durcissement de l'API

En tant que responsable sécurité,
je veux limiter et sécuriser l'accès à l'API,
afin de protéger le service contre les abus et les fuites.

#### Acceptance Criteria

1. Un rate limiting est appliqué sur les endpoints sensibles (notamment `/recognize`).
2. Les erreurs sont normalisées et n'exposent ni stack trace ni donnée interne.
3. Les identifiants clients sont anonymes.
4. Des tests vérifient le déclenchement du rate limiting et le format des erreurs.

---

## Epic 3 — Application mobile Android (parcours complet)

**Objectif étendu :** livrer l'application Flutter Android offrant le parcours utilisateur complet, connectée à l'API. À la fin de cet epic, un locuteur zarma peut enregistrer un nombre, voir ce que le système a compris, confirmer en cas d'ambiguïté, corriger simplement, et consulter son historique — avec une gestion robuste des permissions, des erreurs et des réseaux lents. Cet epic peut fonctionner contre l'API branchée sur `MockRecognizer` tant que l'ASR réel n'est pas déployé.

### Story 3.1 — Fondation de l'app Flutter et navigation

En tant que développeur,
je veux une app Flutter initialisée avec navigation et configuration API,
afin d'avoir un socle mobile prêt à accueillir les écrans.

#### Acceptance Criteria

1. `apps/mobile` est un projet Flutter Android buildable avec la solution de gestion d'état retenue par l'Architect (Riverpod ou Bloc).
2. La navigation entre les écrans principaux (Accueil, Enregistrement, Traitement, Résultat, Confirmation, Correction, Historique) est en place.
3. L'URL de l'API et la configuration proviennent d'une config non secrète ; aucun secret n'est embarqué.
4. Un client HTTP (`dio`) est configuré avec gestion des timeouts et des erreurs réseau.
5. L'app démarre sur l'écran Accueil avec le bouton micro visible.

### Story 3.2 — Enregistrement audio contraint

En tant qu'utilisateur,
je veux enregistrer ma voix simplement et proprement,
afin de fournir un audio exploitable par le système.

#### Acceptance Criteria

1. L'app demande et gère la permission micro (accord, refus, refus permanent) avec messages clairs.
2. L'enregistrement produit du WAV PCM 16 bits mono 16 kHz, borné (idéal 1–8 s, max 10 s) avec retour visuel (niveau, minuterie).
3. L'utilisateur peut annuler l'enregistrement ; le fichier temporaire est supprimé après envoi ou annulation.
4. Un contrôle de taille/durée empêche l'envoi d'audios hors limites.
5. Des tests/vérifications manuelles sur device confirment le format et la suppression du fichier temporaire.

### Story 3.3 — Traitement et écran Résultat

En tant qu'utilisateur,
je veux voir clairement le nombre compris,
afin d'obtenir rapidement mon résultat.

#### Acceptance Criteria

1. Après enregistrement, l'app appelle `/recognize` et affiche un état de traitement avec possibilité d'annuler la requête.
2. En cas de haute confiance, l'écran Résultat affiche le nombre en chiffres et la forme zarma.
3. Les erreurs (réseau lent, timeout, échec serveur) affichent des messages clairs et des options de reprise.
4. La latence perçue est gérée (indicateur d'activité, pas de blocage de l'UI).

### Story 3.4 — Confirmation en cas d'ambiguïté

En tant qu'utilisateur,
je veux confirmer parmi des propositions quand le système hésite,
afin d'éviter une erreur sans avoir à tout ressaisir.

#### Acceptance Criteria

1. Quand la réponse demande confirmation, l'app présente le(s) candidat(s) ordonné(s).
2. L'utilisateur peut sélectionner un candidat, demander à répéter, ou passer en correction manuelle.
3. Le choix de l'utilisateur est renvoyé comme feedback à l'API.
4. Quand la réponse demande répétition (phrase non numérique / trop incertaine), l'app invite à réenregistrer avec un message compréhensible.

### Story 3.5 — Correction manuelle avec forme zarma

En tant qu'utilisateur,
je veux corriger facilement un nombre erroné,
afin de garder le contrôle et de renforcer la fiabilité.

#### Acceptance Criteria

1. L'écran Correction propose un clavier numérique pour saisir le bon nombre.
2. À la saisie, l'app affiche automatiquement la forme zarma canonique (via le générateur, exposé par l'API ou embarqué).
3. La correction est envoyée à `/feedback` avec le contexte (nombre proposé vs corrigé, versions).
4. Les nombres hors plage sont refusés avec un message clair.

### Story 3.6 — Historique

En tant qu'utilisateur,
je veux consulter mes reconnaissances passées,
afin de retrouver et vérifier mes résultats.

#### Acceptance Criteria

1. L'écran Historique liste les reconnaissances récentes (nombre, forme zarma, date) via `/history`.
2. La liste gère les états vide, chargement et erreur.
3. L'affichage fonctionne en connexion lente (chargement progressif / réessai).

---

## Epic 4 — Collecte consentie, feedback & socle de données

**Objectif étendu :** transformer l'usage en ressource durable et éthique. À la fin de cet epic, les utilisateurs consentants peuvent contribuer leur voix via des prompts générés, avec consentement explicite versionné, anonymat, upload, et possibilité de retrait ; les contributions sont validées avant intégration au dataset ; et les corrections/feedbacks alimentent des métriques exploitables. Cet epic constitue le socle de données consenties réutilisable pour le benchmark (Epic 5) et l'amélioration continue.

### Story 4.1 — Consentement explicite versionné

En tant que contributeur,
je veux comprendre et accepter clairement comment ma voix sera utilisée,
afin de contribuer en confiance et de pouvoir me rétracter.

#### Acceptance Criteria

1. Un écran de consentement présente un texte versionné (usage, anonymat, conservation, retrait) avant toute contribution.
2. Le consentement (version acceptée, horodatage, identifiant anonyme) est enregistré.
3. Aucune collecte conservée n'a lieu sans consentement explicite ; l'audio ordinaire reste supprimé par défaut.
4. Le texte et la version du consentement sont traçables côté serveur.

### Story 4.2 — Prompts de contribution et enregistrement consenti

En tant que contributeur,
je veux qu'on me propose quoi prononcer,
afin de fournir des contributions utiles et variées.

#### Acceptance Criteria

1. Le système génère des prompts (nombres à prononcer) couvrant la plage et les cas utiles (paires de confusion, échelles).
2. Le flux de contribution réutilise l'enregistrement contraint (WAV PCM 16 bits mono 16 kHz).
3. Chaque contribution attache des métadonnées (prompt attendu, identifiant anonyme, device/région si fournis, versions).
4. Le consentement valide est requis pour lancer la contribution.

### Story 4.3 — Upload, endpoint `recordings` et stockage sécurisé

En tant que responsable données,
je veux recevoir et stocker les contributions de façon sûre,
afin d'alimenter le dataset sans exposer de données sensibles.

#### Acceptance Criteria

1. `/api/v1/recordings` reçoit les contributions consenties (audio + métadonnées) avec les mêmes contrôles de sécurité audio que `/recognize`.
2. L'audio consenti est stocké en stockage objet/répertoire sécurisé (jamais en base) ; seules les métadonnées vont en base.
3. Les contributions sont marquées « en attente de validation » avant toute intégration au dataset.
4. Les logs ne contiennent aucune donnée sensible.

### Story 4.4 — Retrait des contributions

En tant que contributeur,
je veux pouvoir retirer mes contributions,
afin d'exercer mon droit de rétractation.

#### Acceptance Criteria

1. Un mécanisme permet de demander le retrait des contributions liées à un identifiant anonyme.
2. Le retrait supprime l'audio consenti et marque les métadonnées comme retirées/anonymisées.
3. Les données retirées sont exclues du dataset et des évaluations futures.

### Story 4.5 — Validation avant intégration au dataset

En tant que responsable données,
je veux valider les contributions avant de les intégrer,
afin de préserver la qualité et la représentativité du corpus.

#### Acceptance Criteria

1. Un outil/flux (script ou back-office minimal) permet de revoir les contributions en attente et de les accepter/rejeter.
2. Seules les contributions validées entrent dans le dataset, avec séparation **par locuteur** préservée.
3. Le statut (en attente / validé / rejeté / retiré) est traçable.

### Story 4.6 — Métriques de qualité issues du feedback

En tant que responsable produit,
je veux voir les métriques de production,
afin de piloter la qualité et cibler les améliorations.

#### Acceptance Criteria

1. Les taux de confirmation et de correction sont calculés à partir des feedbacks stockés.
2. Les latences totale et ASR sont mesurées et consultables.
3. La couverture linguistique (éléments `validé` vs `unresolved`) est visible.
4. Les métriques sont exposées de façon lisible (endpoint, log structuré ou tableau de bord minimal).

---

## Epic 5 — Benchmark ASR, sélection du modèle & calibration

**Objectif étendu :** transformer le choix du modèle vocal et le réglage de la confiance en décisions fondées sur les données. À la fin de cet epic, un corpus de benchmark reproductible (split strict par locuteur) permet de comparer CTC vs LLM sur l'Exact Number Accuracy, de produire une matrice de confusions, de sélectionner le modèle du MVP, de brancher le recognizer réel via l'interface existante, et de calibrer les poids/seuils de la confiance composite. Cet epic est **gaté par la décision de ressource GPU** (risque n°1) ; tout ce qui précède peut être livré via `MockRecognizer`.

> **Décision requise (bloquante pour cet epic) :** ressource GPU pour l'ASR — cloud (fournisseur/budget) vs machine locale. Le Mac M1 8 Go ne peut pas servir l'ASR de production.

### Story 5.1 — Corpus de benchmark avec split par locuteur

En tant que responsable données,
je veux un corpus d'évaluation propre et représentatif,
afin de mesurer la qualité sans fuite de données.

#### Acceptance Criteria

1. Le corpus contient ≥ 100 audios, plusieurs locuteurs, nombres courts/longs et paires de confusion.
2. Le jeu de test est séparé **par locuteur** : aucune voix de test n'apparaît ailleurs.
3. Chaque audio est étiqueté avec le nombre attendu (vérité terrain) et des métadonnées (locuteur anonyme, région si connue, condition calme/bruit).
4. Le corpus est reproductible (script de constitution + manifest versionné).

### Story 5.2 — Harnais d'évaluation Exact Number Accuracy

En tant qu'ingénieur,
je veux un harnais d'évaluation automatisé,
afin de comparer objectivement les modèles.

#### Acceptance Criteria

1. Le harnais exécute le pipeline complet (ASR → normalisation → parsing) sur le corpus et calcule l'**Exact Number Accuracy** (métrique de décision, pas le WER).
2. Il produit une **matrice de confusions** des nombres et met en évidence les paires proches.
3. Il mesure les taux de rejet / fausse acceptation et la latence ASR.
4. Les résultats sont reproductibles et exportés (rapport versionné).

### Story 5.3 — Intégration des recognizers réels (CTC & LLM)

En tant qu'ingénieur,
je veux brancher les modèles Omnilingual réels derrière l'interface existante,
afin de les évaluer sans modifier l'API ni l'app.

#### Acceptance Criteria

1. Les implémentations CTC (`omniASR_CTC_300M_v2`, sans `lang`) et LLM (`omniASR_LLM_300M_v2`, `lang=["dje_Latn"]`) respectent l'interface `SpeechRecognizer`.
2. Le service ASR se déploie/redémarre indépendamment de l'API (image Docker ASR lourde séparée).
3. Le passage de Mock à un modèle réel se fait par configuration, sans changement d'API ni de mobile.
4. Un test de fumée confirme une reconnaissance réelle de bout en bout sur la ressource GPU retenue.

### Story 5.4 — Sélection du modèle du MVP

En tant que responsable produit,
je veux choisir le modèle sur des données,
afin d'ancrer la décision dans des preuves reproductibles.

#### Acceptance Criteria

1. CTC et LLM sont comparés sur l'Exact Number Accuracy en conditions calme et bruit modéré (locuteurs non vus).
2. La décision documentée retient le modèle du MVP avec justification chiffrée et matrice de confusions à l'appui.
3. Les objectifs de bêta (≥ 95 % calme, ≥ 90 % bruit modéré) sont évalués et l'écart éventuel est documenté avec plan.
4. La configuration par défaut de l'API pointe vers le modèle retenu.

### Story 5.5 — Calibration de la confiance composite

En tant qu'ingénieur,
je veux calibrer les poids et seuils de confiance sur des données réelles,
afin d'optimiser le compromis acceptation / confirmation / rejet.

#### Acceptance Criteria

1. Les poids (acoustique, grammatical, variante, marge, historique de confusions) et les seuils accepter/confirmer/répéter sont réglés à partir du corpus.
2. La table de confusions ASR est alimentée par les erreurs réelles observées (distincte des variantes linguistiques).
3. Le réglage améliore (ou documente le compromis) le taux de fausse acceptation sans dégrader excessivement l'acceptation correcte.
4. Les valeurs calibrées sont versionnées et rechargées par l'API sans changement de code applicatif.

---

## Checklist Results Report

*(À compléter : exécuter la `pm-checklist` après validation du PRD par le porteur du projet. Non exécutée à ce stade — document généré en mode YOLO, en attente de revue.)*

---

## Next Steps

### UX Expert Prompt

Concevoir l'UX/UI mobile Android de « Zarma — reconnaissance des nombres » à partir de ce PRD. Cible : utilisateurs zarma à alphabétisation variable, geste micro unique, boucle confirmation/correction rassurante, WCAG AA, affichage systématique de la forme zarma à côté des chiffres. Livrer les spécifications des écrans Accueil, Enregistrement, Traitement, Résultat, Confirmation, Correction, Historique et flux Contribution/Consentement.

### Architect Prompt

Concevoir l'architecture technique à partir de ce PRD. Décisions attendues : **Riverpod vs Bloc** (une seule solution) ; découpage monorepo (Flutter / API FastAPI / service ASR / paquet `zarma_numbers`) ; contrats API et schéma de données (audio hors base) ; interface `SpeechRecognizer` (Mock/CTC/LLM) ; **stratégie de déploiement GPU pour l'ASR** (cloud vs local — risque n°1) ; Docker (images API légère / ASR lourde), nginx, HTTPS, environnements local/staging/prod ; et garantie que le moteur linguistique et l'API (via Mock) restent développables sans GPU.