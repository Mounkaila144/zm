# Coding Standards

> Extrait fidèle de `docs/architecture.md` — sections « Coding Standards », « Security Requirements » et « Development Commands ».

## Critical Fullstack Rules

- **Isolation du moteur linguistique :** `packages/zarma_numbers` ne doit **jamais** importer FastAPI, httpx, SQLAlchemy ni quoi que ce soit d'ASR. Toute conversion nombre↔zarma passe par ce paquet — aucune règle numérique dupliquée ailleurs.
- **Jamais de nombre inventé :** ni le parseur, ni l'API, ni le mobile ne produisent un nombre pour un texte non numérique — retour vide/`repeat` (FR21). Interdiction de tout fuzzy matching décisionnel (Levenshtein aveugle) pour trancher un nombre (NFR14).
- **Variantes ≠ corrections ASR :** deux structures distinctes. La normalisation utilise la table de variantes linguistiques ; les corrections d'erreurs ASR (calibrées en Epic 5) ne s'y mélangent jamais (FR8).
- **Versions systématiques :** toute réponse et toute ligne persistée portent `model_version` + `grammar_version` (NFR12).
- **ASR via l'interface uniquement :** l'API n'appelle jamais un modèle directement — toujours à travers `SpeechRecognizer`. Changer de modèle = changer une config, pas du code applicatif (NFR9).
- **Audio hors base + suppression par défaut :** aucun audio en base ; l'audio de `/recognize` est supprimé après traitement ; seul l'audio consenti est conservé (FR20/FR22).
- **Config via objet settings :** accès aux variables d'env uniquement via l'objet `settings` (Pydantic), jamais `os.environ` dispersé ; aucun secret en dur (NFR3).
- **Erreurs sans fuite :** toutes les routes passent par le handler d'erreurs normalisé — pas de stack trace ni de donnée interne exposée (NFR6, story 2.7).
- **État mobile via Riverpod :** aucune logique métier/async dans les widgets ; passer par les providers.

## Naming Conventions

| Element | Frontend (Dart) | Backend (Python) | Example |
|---------|-----------------|------------------|---------|
| Fichiers/modules | snake_case | snake_case | `result_screen.dart` / `recognize.py` |
| Classes | PascalCase | PascalCase | `RecognitionResult` / `MockRecognizer` |
| Providers | camelCase + `Provider` | — | `recognitionProvider` |
| Fonctions/vars | camelCase | snake_case | `recognize()` / `composite_confidence()` |
| API Routes | — | kebab-case | `/api/v1/grammar/version` |
| Tables DB | — | snake_case | `recognitions`, `contributions` |

## Security Requirements

**Frontend Security :**
- CSP Headers : N/A (app native) ; pas de WebView pour contenu distant.
- XSS/Injection : entrées numériques bornées côté client, revalidées côté serveur.
- Secure Storage : `anon_id` local non sensible ; **aucun secret embarqué** (NFR3) ; audio temporaire supprimé après envoi/annulation (FR2).

**Backend Security :**
- Input Validation : Pydantic + contrôles audio (MIME réel, décodage, taille ≤ ~2 Mo, conversion 16kHz, refus corrompus, aucune exécution — NFR5).
- Rate Limiting : slowapi sur `/recognize` et `/recordings` (NFR4).
- CORS : restreint aux origines attendues ; HTTPS obligatoire via nginx (NFR3).
- Logs : structlog sans PII ni audio (NFR6).

**Authentication Security :**
- Token Storage : secret endpoint ASR côté serveur uniquement (`.env`/secrets), jamais côté mobile.
- Session : sans état (anon_id) ; pas de mot de passe au MVP.
- Anonymisation & retrait : contributions anonymes, retrait supprime l'audio et anonymise les métadonnées (NFR7, story 4.4).

## Development Commands

```bash
# Tout (API + DB) via Docker en dev
make up

# Moteur linguistique seul (sans GPU, sans API)
uv run pytest packages/zarma_numbers

# API seule (MockRecognizer, ASR_MODE=mock)
uv run uvicorn app.main:app --reload --app-dir services/api

# Mobile (contre l'API locale)
cd apps/mobile && flutter run

# Tests
uv run pytest packages/zarma_numbers services/api
cd apps/mobile && flutter test
make invariant
```

