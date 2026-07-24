# Epic 1 — Fondations & Moteur linguistique déterministe

**Objectif étendu :** établir toute la fondation projet (monorepo, gestion de version, CI, qualité de code) et livrer le cœur du produit : un moteur linguistique zarma déterministe et réversible, adossé à un lexique v1 validé par des locuteurs natifs. À la fin de cet epic, on dispose d'un paquet Python autonome capable de convertir nombre ↔ zarma sur `0`–`1 000 000`, prouvé par l'invariant `parse(generate(n)) == n`, sans dépendre d'un GPU, de l'ASR, de l'API ou du mobile — ce qui dérisque immédiatement le projet.

## Story 1.1 — Initialisation du monorepo et de l'outillage

En tant que développeur,
je veux un monorepo initialisé avec la structure de dossiers, le contrôle de version et l'outillage qualité,
afin de disposer d'une base saine et cohérente pour toutes les couches du projet.

### Acceptance Criteria

1. Le dépôt contient la structure `apps/mobile`, `services/api`, `services/asr`, `packages/zarma_numbers`, `dataset/`, `docs/`, `infrastructure/`, `scripts/`.
2. Git est initialisé avec `.gitignore` approprié (Python, Flutter, `.env`, artefacts) et `.env.example` fourni ; aucun secret n'est committé.
3. L'outillage qualité Python (formatteur, linter, exécuteur de tests) est configuré et exécutable localement.
4. Une pipeline CI exécute lint + tests du paquet `zarma_numbers` à chaque push.
5. Un README racine décrit la structure du monorepo et les commandes de base.

## Story 1.2 — Spécification et validation du système numérique zarma v1

En tant que responsable produit,
je veux formaliser le système numérique zarma et le faire valider par des locuteurs natifs,
afin de figer des formes canoniques fiables avant de coder la grammaire.

### Acceptance Criteria

1. `docs/numeration-zarma-v1.md` documente unités, dizaines, échelles, connecteurs et exemples couvrant `0`–`999 999`.
2. Un protocole de validation est appliqué avec au moins 3 locuteurs natifs selon une règle de décision explicite (unanimité / majorité 2 sur 3).
3. Les formes de **10 000, 100 000 et 1 000 000** sont traitées en priorité et chacune est soit résolue (forme canonique retenue), soit explicitement marquée bloquante.
4. Les variantes régionales/orthographiques reconnues (`iddou`/`iddu`, `iyega`/`yega`, `zangou`/`zangu`, `nda`/`da`, etc.) sont recensées et conservées, jamais inventées ni supprimées arbitrairement.
5. Le document indique clairement le statut de chaque forme (`validé` / `unresolved`) et la règle de décision utilisée.

## Story 1.3 — Lexique versionné `lexicon.yaml`

En tant que développeur,
je veux un lexique numérique zarma versionné et chargeable,
afin que la grammaire s'appuie sur une source de vérité unique et traçable.

### Acceptance Criteria

1. `lexicon.yaml` encode unités, dizaines, échelles, connecteurs et variantes, chaque entrée portant un statut (`validé` / `unresolved`).
2. Le lexique porte un numéro de version (`grammar_version`) exposable par le code.
3. Un chargeur valide la structure du lexique au démarrage et échoue proprement si une entrée requise est manquante ou incohérente.
4. Les variantes linguistiques et les corrections d'erreurs ASR sont stockées dans **deux structures distinctes**.
5. Des tests vérifient le chargement, le versionnage et la séparation variantes vs corrections ASR.

## Story 1.4 — Générateur `nombre → zarma`

En tant qu'utilisateur du moteur,
je veux obtenir la forme zarma canonique d'un nombre,
afin d'afficher la prononciation correcte et de préparer la future réponse orale.

### Acceptance Criteria

1. `generator.py` produit la forme zarma canonique pour tout entier de `0` à `1 000 000` (dans les limites des formes validées).
2. Les connecteurs et règles de composition suivent la grammaire documentée en 1.2.
3. Les nombres hors plage ou invalides sont refusés avec une erreur explicite.
4. Des tests couvrent des cas représentatifs (unités, dizaines, centaines, milliers, échelles, cas limites `0`, `10 000`, `100 000`, `1 000 000`).

## Story 1.5 — Normaliseur de texte

En tant que développeur,
je veux normaliser un texte zarma brut avant analyse,
afin d'absorber les variations d'orthographe et de casse sans corrompre le sens numérique.

### Acceptance Criteria

1. `normalizer.py` normalise casse, espaces, connecteurs et orthographes alternatives connues vers des formes canoniques.
2. La normalisation s'appuie sur la table de variantes linguistiques (jamais sur du fuzzy matching décisionnel).
3. La normalisation est idempotente (`normalize(normalize(x)) == normalize(x)`).
4. Des tests couvrent variantes orthographiques, connecteurs et entrées non numériques.

## Story 1.6 — Parseur `zarma → nombre` et invariant exhaustif

En tant qu'utilisateur du moteur,
je veux convertir un texte zarma en nombre de façon fiable et prouvée,
afin de garantir l'exactitude du cœur du produit indépendamment de l'ASR.

### Acceptance Criteria

1. `parser.py` analyse un texte zarma normalisé et retourne l'entier correspondant, ou une absence de résultat explicite si le texte n'est pas un nombre valide.
2. Le parseur ne devine ni n'invente jamais un nombre à partir d'un texte non numérique (retour vide/erreur, jamais une valeur arbitraire).
3. `validator.py` exécute l'invariant `parse(generate(n)) == n` sur **toute la plage** `0`–`1 000 000` et le test passe (sur les formes validées ; les formes `unresolved` sont explicitement tracées).
4. La couverture inclut les paires de confusion connues (`hinka`/`hinza`, `iyye`/`yega`, `iddu`/`iyye`) traitées comme distinctes.
5. La CI exécute l'invariant et échoue si une forme validée le viole.

---

## Story 1.7 — Grandes échelles ≥ 100 000 (marqueur `dala`) & forme million

_(Ajoutée via `/correct-course` le 2026-07-24 — voir `docs/sprint-change-proposal-2026-07-24-grandes-echelles-dala.md`.)_

En tant qu'utilisateur du moteur,
je veux convertir sans ambiguïté les nombres jusqu'à 1 000 000,
afin que le moteur couvre toute la plage cible avec l'invariant prouvé.

### Acceptance Criteria

1. Le lexique intègre le marqueur `dala`, résout la forme `million`, et bumpe `grammar_version` (→ `1.1.0`).
2. Le générateur désambiguïse `≥ 100 000` via `dala` (reste après multiplicateur multiple de 100) ; `1 000 000 = million`.
3. Le parseur reconnaît `dala` et `million` ; `parse` reste l'inverse exact du générateur.
4. L'invariant `parse(normalize(generate(n))) == n` est prouvé sur **toute** la plage `0`–`1 000 000` (0 violation).
5. La CI exécute l'invariant complet (`make invariant`).

> ⚠️ **Gate de gouvernance :** validé par 1 locuteur (Session 1) ; formes en statut `unresolved` tant que < 3 locuteurs (règle de décision, `docs/numeration-zarma-v1.md` §1).

---
