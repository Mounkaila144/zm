# Tech Stack

> Extrait fidèle de `docs/architecture.md` — section « Tech Stack ».

Ceci est la **sélection technologique définitive** du projet. Tout le développement doit utiliser ces choix et versions.

| Category | Technology | Version | Purpose | Rationale |
|----------|-----------|---------|---------|-----------|
| Frontend Language | Dart | 3.5.x | Langage app mobile | Requis par Flutter, typage sain, null-safety |
| Frontend Framework | Flutter | 3.24.x (stable) | App Android MVP | Imposé PRD ; un seul codebase, perf native audio |
| UI Component Library | Material 3 (Flutter built-in) | — | Composants UI accessibles | WCAG AA, cibles tactiles larges, thème sobre |
| State Management | **Riverpod** | 2.5.x | Gestion d'état / DI | **Décision Architect** : testable, DI intégrée, pas de boilerplate Bloc, providers pour async (recognize/history) |
| Backend Language | Python | 3.11.x | API + moteur linguistique | Imposé PRD (NFR15) |
| Backend Framework | FastAPI | 0.115.x | API REST asynchrone | Imposé PRD ; OpenAPI natif, Pydantic, async I/O |
| Validation / Schemas | Pydantic | 2.9.x | Schémas requêtes/réponses | Validation stricte des entrées (NFR5), contrats typés |
| Linguistic Engine | Paquet `zarma_numbers` | 0.1.0 | texte↔nombre déterministe | Cœur produit, autonome (NFR8) |
| API Style | REST (OpenAPI 3.0) | 3.0 | Contrat mobile↔API | multipart pour `/recognize` (FR10), doc auto |
| Database (dev) | SQLite | 3.x | Persistance locale dev | FR22, zéro service à lancer en dev |
| Database (prod) | PostgreSQL | 16.x | Persistance production | FR22, robustesse, JSONB pour métadonnées |
| ORM / Migrations | SQLAlchemy + Alembic | 2.0.x / 1.13.x | Accès données + migrations | Repository pattern, migrations versionnées (FR22) |
| ASR Runtime | Meta Omnilingual ASR | omniASR_CTC_300M_v2 / omniASR_LLM_300M_v2 | audio→texte `dje_Latn` | Apache 2.0, support zarma, choix final après benchmark (Epic 5) |
| ASR ML deps | PyTorch + transformers/fairseq2 | selon modèle | Inference modèle | Python `>=3.10,<3.14` (NFR15), isolé côté serverless |
| ASR Hosting | **Modal** (serverless GPU) | — | Endpoint inference managé | Décision utilisateur : pay-per-use, scale-to-zero, modèle Python arbitraire, pas d'ops GPU |
| Audio (mobile) | `record`, `path_provider` | 5.x / 2.x | Capture WAV PCM16 mono 16kHz | Imposé PRD (FR1) |
| HTTP client (mobile) | `dio` | 5.x | Appels API, timeouts, retry | Imposé PRD, intercepteurs erreurs réseau |
| File Storage | Répertoire chiffré VPS / S3-compatible (option MinIO) | — | Audio consenti uniquement | Audio hors base (FR22), suppression par défaut (FR20) |
| Authentication | Identifiant anonyme (device UUID) + clé API front non secrète | — | Anonymat contributeurs | NFR7 ; pas d'auth utilisateur MVP, HTTPS + rate limit |
| Rate Limiting | slowapi (starlette-limiter) | 0.1.x | Protection `/recognize`, `/recordings` | NFR4, story 2.7 |
| Frontend Testing | flutter_test + mocktail | SDK / 1.x | Widgets, flux correction | Testing Requirements PRD |
| Backend Testing | pytest + httpx + pytest-asyncio | 8.x | Unitaires + intégration (Mock) | Invariant exhaustif, endpoints sans GPU |
| Linguistic Testing | pytest + hypothesis | 8.x / 6.x | Invariant + property-based | `parse(generate(n))==n` sur 0–1 000 000 |
| E2E Testing | pytest (harnais benchmark) + tests manuels device | — | Exact Number Accuracy (Epic 5) | Harnais d'évaluation, pas test unitaire |
| Python tooling | uv + ruff + black | latest | Deps, lint, format | Rapide, reproductible, workspace multi-paquets |
| Build/Deploy | Docker + Docker Compose | 27.x / v2 | Images API légère / infra | NFR13, images séparées |
| IaC / Config | docker-compose + `.env` + nginx conf versionnées | — | Infra déclarative légère | Suffisant pour VPS mono-nœud MVP |
| CI/CD | GitHub Actions | — | lint + tests à chaque push | Story 1.1 AC4, sans GPU |
| Monitoring | Logs structurés (structlog) + Uptime Kuma + `/health` | — | Observabilité MVP | NFR6 (logs sans données sensibles), NFR1 (latences) |
| Logging | structlog (JSON) | 24.x | Logs sans PII | NFR6 |
| Secrets | `.env` hors Git + secrets provider (Modal secrets) | — | Clés endpoint ASR | NFR3 |

