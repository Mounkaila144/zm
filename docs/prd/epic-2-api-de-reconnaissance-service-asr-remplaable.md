# Epic 2 — API de reconnaissance & Service ASR remplaçable

**Objectif étendu :** exposer le moteur linguistique via une API FastAPI robuste et sécurisée, avec une couche ASR abstraite et remplaçable. À la fin de cet epic, un client peut envoyer un audio et recevoir nombre + texte normalisé + confiance + alternatives + versions, avec une politique d'ambiguïté prudente, une persistance conforme (audio hors base) et une sécurité de base — le tout démontrable de bout en bout avec `MockRecognizer`, sans GPU.

## Story 2.1 — Squelette API FastAPI, `/health` et versions

En tant que développeur,
je veux une API FastAPI démarrable exposant santé et versions,
afin d'établir la couche service et sa traçabilité dès le départ.

### Acceptance Criteria

1. `services/api` démarre via FastAPI et expose `/health` retournant un statut OK.
2. `/api/v1/grammar/version` retourne la `grammar_version` issue du lexique, et `/api/v1/models` liste les recognizers disponibles.
3. La documentation OpenAPI est générée et accessible.
4. La configuration provient de variables d'environnement (`.env` hors Git) ; aucun secret n'est en dur.
5. Des tests d'intégration couvrent `/health`, `/models`, `/grammar/version`.

## Story 2.2 — Interface `SpeechRecognizer` et `MockRecognizer`

En tant qu'architecte,
je veux une abstraction de reconnaissance vocale avec une implémentation Mock,
afin de développer et tester l'API sans dépendre d'un GPU ni d'un modèle réel.

### Acceptance Criteria

1. Une interface `SpeechRecognizer` définit un contrat clair (audio → texte + signaux acoustiques/métadonnées).
2. `MockRecognizer` retourne des transcriptions déterministes configurables pour les tests.
3. Le service ASR est isolé de l'API (paquet/module séparé), sélectionnable par configuration.
4. Des tests valident le contrat de l'interface et le comportement du Mock.

## Story 2.3 — Endpoint `/recognize` (pipeline complet via Mock)

En tant qu'utilisateur,
je veux envoyer un audio et recevoir le nombre compris,
afin d'obtenir le résultat de reconnaissance de bout en bout.

### Acceptance Criteria

1. `/api/v1/recognize` accepte du `multipart/form-data` (fichier audio) et enchaîne ASR → normalisation → parsing.
2. La réponse contient : nombre, texte normalisé, score de confiance, alternatives, `model_version`, `grammar_version`.
3. La validation d'entrée est faite par Pydantic ; les entrées invalides renvoient des erreurs claires.
4. Un timeout est appliqué et les erreurs internes ne fuient aucune donnée sensible.
5. Des tests d'intégration couvrent le pipeline avec `MockRecognizer` (cas nombre valide, texte non numérique rejeté, audio invalide).

## Story 2.4 — Validation et traitement sécurisés de l'audio

En tant que responsable sécurité,
je veux des contrôles serveur stricts sur l'audio reçu,
afin d'éviter les fichiers malveillants et de garantir un format exploitable.

### Acceptance Criteria

1. Le serveur vérifie le MIME réel, décode l'audio, et refuse les fichiers corrompus ou trop volumineux (≤ ~2 Mo).
2. L'audio est converti/normalisé en mono 16 kHz avant traitement.
3. Le fichier audio n'est jamais exécuté et est traité dans un contexte isolé.
4. Par défaut, l'audio ordinaire est supprimé après traitement (aucune conservation sans consentement).
5. Des tests couvrent un fichier valide, un fichier corrompu, un fichier trop gros et un MIME incohérent.

## Story 2.5 — Confiance composite et politique d'ambiguïté

En tant qu'utilisateur,
je veux que le système hésite plutôt que de se tromper,
afin de garder le contrôle et d'éviter les erreurs numériques silencieuses.

### Acceptance Criteria

1. Un score de confiance composite combine signaux acoustique, grammatical, variante connue, marge entre candidats et historique de confusions.
2. La politique produit une décision explicite : accepter / demander confirmation / demander répétition.
3. En cas d'ambiguïté, la réponse inclut les alternatives candidates ordonnées.
4. Le système ne retourne jamais un nombre pour une phrase non numérique (rejet ou répétition).
5. Les poids/seuils sont configurables (valeurs par défaut documentées ; calibration réelle en Epic 5).
6. Des tests couvrent haute confiance, ambiguïté (deux candidats proches) et rejet.

## Story 2.6 — Persistance, historique et feedback

En tant que responsable produit,
je veux persister reconnaissances, historique et feedbacks,
afin de suivre la qualité et d'alimenter l'amélioration continue.

### Acceptance Criteria

1. La base est SQLite en dev et PostgreSQL en prod, avec migrations Alembic ; l'audio n'est jamais stocké en base.
2. Chaque reconnaissance persistée conserve au minimum `model_version` et `grammar_version`.
3. `/api/v1/history` retourne l'historique des reconnaissances d'un identifiant anonyme.
4. `/api/v1/feedback` enregistre les corrections/feedbacks utilisateur.
5. Les logs ne contiennent aucune donnée sensible ; des tests couvrent l'écriture et la relecture de l'historique et du feedback.

## Story 2.7 — Rate limiting et durcissement de l'API

En tant que responsable sécurité,
je veux limiter et sécuriser l'accès à l'API,
afin de protéger le service contre les abus et les fuites.

### Acceptance Criteria

1. Un rate limiting est appliqué sur les endpoints sensibles (notamment `/recognize`).
2. Les erreurs sont normalisées et n'exposent ni stack trace ni donnée interne.
3. Les identifiants clients sont anonymes.
4. Des tests vérifient le déclenchement du rate limiting et le format des erreurs.

---
