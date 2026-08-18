.DEFAULT_GOAL := help
.PHONY: help setup dev dev-backend dev-frontend migrate migrations superuser \
        test test-backend test-frontend lint format check build clean \
        regenerate-goldens check-fixtures migrations-check inspect \
        docker-up docker-down

BACKEND := cd backend && poetry run
FRONTEND := cd frontend &&

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- Setup ------------------------------------------------------------------

setup: ## One-time setup: install deps and create the databases
	@command -v poetry >/dev/null || { echo "poetry not found: https://python-poetry.org/docs/#installation"; exit 1; }
	@pg_isready -q || { echo "Postgres is not running. Try: brew services start postgresql@14"; exit 1; }
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")
	cd backend && poetry install
	cd frontend && npm install
	@createdb expense_analyser 2>/dev/null || echo "Database expense_analyser already exists"
	@createdb expense_analyser_test 2>/dev/null || echo "Database expense_analyser_test already exists"
	$(BACKEND) python manage.py migrate
	@echo ""
	@echo "Setup complete. Run 'make dev' and open http://localhost:5173"

# --- Development ------------------------------------------------------------

dev: ## Run backend and frontend together
	@echo "Backend  → http://127.0.0.1:8000"
	@echo "Frontend → http://localhost:5173  (proxies /api to the backend)"
	@trap 'kill 0' EXIT INT TERM; \
	$(MAKE) dev-backend & $(MAKE) dev-frontend & wait

dev-backend: ## Run the Django dev server on :8000
	$(BACKEND) python manage.py runserver 8000

dev-frontend: ## Run the Vite dev server on :5173
	$(FRONTEND) npm run dev

migrate: ## Apply database migrations
	$(BACKEND) python manage.py migrate

migrations: ## Generate migrations for model changes
	$(BACKEND) python manage.py makemigrations

superuser: ## Create an admin user
	$(BACKEND) python manage.py createsuperuser

# --- Quality ----------------------------------------------------------------

regenerate-goldens: ## Rebuild parser golden files (BANK=hdfc to narrow) — read the diff!
	$(BACKEND) python manage.py regenerate_goldens \
		--settings=config.settings.test $(if $(BANK),--bank $(BANK),)

check-fixtures: ## Scan parser fixtures for personal data
	python3 scripts/check_fixtures_anonymised.py

test: test-backend test-frontend ## Run all tests

test-backend: ## Run the Python test suite
	$(BACKEND) pytest

inspect: ## Diagnose a statement file: make inspect FILE=~/statement.pdf [PASSWORD=x]
	@test -n "$(FILE)" || { echo "Usage: make inspect FILE=~/statement.pdf [PASSWORD=xxxx]"; exit 1; }
	@# abspath: the recipe cds into backend/, so a path relative to the repo
	@# root would otherwise resolve against the wrong directory.
	$(BACKEND) python manage.py inspect_statement "$(abspath $(FILE))" \
		$(if $(PASSWORD),--password "$(PASSWORD)",)

migrations-check: ## Fail if a model change has no migration
	$(BACKEND) python manage.py makemigrations --check --dry-run \
		--settings=config.settings.test

test-frontend: ## Typecheck the frontend
	$(FRONTEND) npx tsc --noEmit

lint: ## Lint backend and frontend
	$(BACKEND) ruff check .
	$(BACKEND) ruff format --check .
	$(FRONTEND) npm run lint

format: ## Auto-format the code
	$(BACKEND) ruff format .
	$(BACKEND) ruff check . --fix

check: lint migrations-check test ## What CI runs — do this before opening a PR

build: ## Build the production frontend bundle
	$(FRONTEND) npm run build

clean: ## Remove build artefacts and caches
	rm -rf frontend/dist backend/staticfiles backend/.pytest_cache
	find backend -type d -name __pycache__ -prune -exec rm -rf {} +

# --- Deployment (self-hosters; not needed for development) -------------------

docker-up: ## Start the self-hosted stack
	docker compose -f deploy/docker-compose.yml up --build

docker-down: ## Stop the self-hosted stack
	docker compose -f deploy/docker-compose.yml down
