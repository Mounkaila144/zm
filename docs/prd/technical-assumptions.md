# Technical Assumptions

## Repository Structure: Monorepo

Monorepo `zarma-numbers/` regroupant : `apps/mobile` (Flutter), `services/api` (FastAPI), `services/asr` (Omnilingual), `packages/zarma_numbers` (moteur linguistique), `dataset/`, `docs/`, `infrastructure/`, `scripts/`. Justification : cohérence des versions (grammaire/lexique), partage de contrats API, développeur solo, et découplage logique via des paquets/services séparés au sein d'un seul dépôt.

## Service Architecture

**Trois couches découplées au sein du monorepo** : Flutter ↔ API FastAPI ↔ service ASR séparé, le tout s'appuyant sur le paquet moteur linguistique. Justification : le service ASR (lourd, GPU) se déploie et redémarre indépendamment de l'API (légère) ; le moteur linguistique fonctionne sans ASR ; l'interface `SpeechRecognizer` rend le modèle vocal remplaçable. Ce n'est pas du microservices « distribué » complet, mais une séparation nette des responsabilités et des cycles de déploiement.

## Testing Requirements

**Unit + Integration**, avec exigence spéciale sur le moteur linguistique. Justification :
- Moteur linguistique : tests unitaires exhaustifs, dont l'**invariant `parse(generate(n)) == n` sur toute la plage** `0`–`1 000 000`, tests de normalisation et de variantes.
- API : tests d'intégration des endpoints avec `MockRecognizer` (aucun GPU requis), validation des schémas Pydantic, gestion d'erreurs, rate limiting.
- Benchmark ASR : évaluation reproductible sur jeu de test **séparé par locuteur** (métrique Exact Number Accuracy, matrice de confusions) — traité comme harnais d'évaluation, pas comme test unitaire.
- Mobile : tests des widgets/écrans clés et du flux de correction ; tests manuels de convenance sur device réel pour l'audio.

## Additional Technical Assumptions and Requests

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
