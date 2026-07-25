# Source Tree

> Extrait fidèle de `docs/architecture.md` — sections « Backend Architecture » et « Unified Project Structure ».

## Backend Controller/Route Organization

```text
services/api/app/
├── main.py                     # app FastAPI, middlewares, routers, lifespan
├── config.py                   # settings Pydantic (env), pas de secret en dur
├── api/v1/
│   ├── health.py               # /health
│   ├── models.py               # /models
│   ├── grammar.py              # /grammar/version
│   ├── recognize.py            # /recognize (pipeline)
│   ├── feedback.py             # /feedback
│   ├── history.py              # /history
│   ├── recordings.py           # /recordings, /recordings/withdraw
│   └── consent.py              # /consent
├── pipeline/
│   ├── audio.py                # validation MIME, décodage, conversion 16kHz
│   ├── confidence.py           # score composite (poids configurables)
│   └── policy.py               # accept | confirm | repeat
├── asr/
│   ├── base.py                 # SpeechRecognizer (Protocol/ABC)
│   ├── mock.py                 # MockRecognizer
│   ├── remote.py               # RemoteCtc/LlmRecognizer (httpx -> Modal)
│   └── factory.py              # sélection par config (mock|ctc|llm)
├── db/
│   ├── session.py              # engine SQLite/PostgreSQL
│   ├── models.py               # SQLAlchemy ORM
│   └── repositories.py         # Repository pattern
├── storage/
│   └── audio_store.py          # écriture/suppression audio consenti (hors base)
└── core/
    ├── errors.py               # handler d'erreurs normalisé (sans PII)
    ├── logging.py              # structlog JSON
    └── rate_limit.py           # slowapi
```

## Unified Project Structure

```text
zarma-numbers/
├── .github/
│   └── workflows/
│       └── ci.yaml                 # lint + tests zarma_numbers + API (Mock), sans GPU
├── apps/
│   └── mobile/                     # App Flutter Android (Riverpod)
│       ├── lib/                    # cf. Frontend Architecture
│       ├── test/                   # flutter_test + mocktail
│       ├── android/
│       └── pubspec.yaml
├── services/
│   ├── api/                        # FastAPI (léger, sans GPU)
│   │   ├── app/                    # cf. Backend Architecture
│   │   ├── tests/                  # pytest (intégration via MockRecognizer)
│   │   ├── alembic/                # migrations
│   │   ├── Dockerfile              # image API légère
│   │   └── pyproject.toml
│   └── asr/                        # Service modèle ASR (serverless GPU)
│       ├── app/                    # Modal app : chargement CTC/LLM, /transcribe
│       ├── tests/                  # smoke tests (Epic 5)
│       └── pyproject.toml
├── packages/
│   └── zarma_numbers/              # Paquet autonome (cœur déterministe)
│       ├── src/zarma_numbers/
│       │   ├── lexicon.yaml        # lexique versionné (validé/unresolved)
│       │   ├── loader.py           # chargement + grammar_version
│       │   ├── normalizer.py
│       │   ├── generator.py
│       │   ├── parser.py
│       │   ├── validator.py        # invariant parse(generate(n))==n
│       │   └── exceptions.py
│       ├── tests/                  # pytest + hypothesis
│       └── pyproject.toml
├── dataset/
│   ├── raw/                        # (git-ignored) audio consenti
│   ├── manifests/                  # manifest versionné, split par locuteur
│   └── benchmark/                  # corpus d'évaluation (Epic 5)
├── infrastructure/
│   ├── docker-compose.yml          # api + postgres + nginx
│   ├── docker-compose.staging.yml
│   ├── nginx/                      # conf reverse proxy + TLS
│   └── backup/                     # scripts de sauvegarde PostgreSQL
├── scripts/                        # bootstrap, seed, bench, deploy
├── docs/
│   ├── prd.md
│   ├── architecture.md             # ce document
│   └── architecture/               # shards générés
├── .env.example                    # gabarit variables (aucun secret réel)
├── .gitignore                      # Python, Flutter, .env, dataset/raw, artefacts
├── Makefile                        # cibles transverses (lint, test, up, migrate)
├── pyproject.toml                  # uv workspace (racine Python)
└── README.md
```

