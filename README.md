# Zarma

Reconnaissance et conversion **texte↔nombre en zarma**, du moteur linguistique
déterministe jusqu'à l'application mobile.

## Principe directeur

> **Séparation stricte** entre le **moteur linguistique déterministe**
> (`packages/zarma_numbers`, testable **sans GPU**) et le **moteur vocal**
> (ASR, **remplaçable**).

Tout ce qui n'est pas l'ASR réel doit être développable et testable sans GPU.
Le paquet `zarma_numbers` n'importe **jamais** FastAPI, httpx, SQLAlchemy ni
aucune dépendance ASR.

## Structure du monorepo

```
zarma/
├── .github/workflows/ci.yaml   # CI : lint + tests zarma_numbers (sans GPU)
├── apps/
│   └── mobile/                 # App Flutter Android (Riverpod) — Epic 3
├── services/
│   ├── api/                    # API FastAPI (léger, sans GPU) — Epic 2
│   └── asr/                    # Service modèle ASR (serverless GPU) — Epic 4
├── packages/
│   └── zarma_numbers/          # Cœur déterministe texte↔nombre (autonome)
│       ├── src/zarma_numbers/  # __version__ ; modules réels en 1.3–1.6
│       └── tests/              # pytest + hypothesis
├── dataset/
│   ├── raw/                    # audio consenti (git-ignored)
│   ├── manifests/              # manifeste versionné, split par locuteur
│   └── benchmark/              # corpus d'évaluation (Epic 5)
├── infrastructure/             # docker-compose, nginx, backup (plus tard)
├── scripts/                    # bootstrap, seed, bench, deploy (plus tard)
├── docs/                       # prd.md, architecture.md, prd/, stories/
├── .env.example                # gabarit variables (aucun secret réel)
├── Makefile                    # cibles transverses (lint, test, up, migrate)
├── pyproject.toml              # workspace uv (racine Python)
└── README.md
```

## Prérequis

- **Python 3.11** + [`uv`](https://docs.astral.sh/uv/) (gestion des dépendances)
- **Flutter 3.24** (app mobile — Epic 3)
- **Docker** + Docker Compose (déploiement — préparé, non requis en story 1.1)

`uv` télécharge et gère lui-même l'interpréteur Python 3.11 (voir
`.python-version`).

## Commandes de base

```bash
# Setup initial (installe le workspace + le cœur en editable)
uv sync

# Lint + vérification de format
make lint            # = uv run ruff check .  +  uv run black --check .

# Tests du paquet cœur
make test            # = uv run pytest packages/zarma_numbers
uv run pytest packages/zarma_numbers

# Formatage automatique
make format
```

`make help` liste toutes les cibles disponibles (dont les placeholders
`up` / `migrate` / `invariant` implémentés dans des stories ultérieures).

## Méthode

Projet piloté avec **BMAD-METHOD**. Flux :
`/analyst` → `/pm` → `/architect` → `/po` → `/sm` → `/dev` → `/qa`.
Voir `CLAUDE.md` et `docs/`.
