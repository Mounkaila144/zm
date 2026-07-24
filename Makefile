# Makefile racine du monorepo Zarma.
# Coordination polyglotte (pas de Nx/Turborepo) : cibles transverses via make + uv.

.DEFAULT_GOAL := help
.PHONY: help lint format test up migrate invariant

help: ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

lint: ## Lint + vérification de format (ruff + black)
	uv run ruff check .
	uv run black --check .

format: ## Applique le formatage (black) et les autofix ruff
	uv run ruff check --fix .
	uv run black .

test: ## Exécute les tests du paquet cœur zarma_numbers
	uv run pytest packages/zarma_numbers

demo: ## Lance le CLI interactif zarma <-> nombre
	uv run python scripts/zarma.py

# --- Cibles placeholder (implémentées dans des stories ultérieures) ---

up: ## [placeholder] Démarre la stack locale (docker compose) — Epic 2+
	@echo "TODO(story ultérieure): docker compose up (services/api, db, etc.)"

migrate: ## [placeholder] Applique les migrations DB — Epic 2
	@echo "TODO(story ultérieure): migrations Alembic pour services/api"

invariant: ## Vérifie l'invariant exhaustif parse(generate(n))==n sur 0..1 000 000
	uv run python -c "import sys; from zarma_numbers.validator import main; sys.exit(main())"
