# zarma_numbers

Paquet Python autonome : cœur **déterministe** de conversion texte↔nombre en
zarma. Testable **sans GPU**, sans aucune dépendance FastAPI / ASR / DB.

## Installation (via le workspace uv racine)

```bash
uv sync
uv run pytest packages/zarma_numbers
```

Modules à venir (stories 1.3–1.6) : `loader`, `normalizer`, `generator`,
`parser`, `validator`.
