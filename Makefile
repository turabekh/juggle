# Juggle developer shortcuts. Backend commands run inside apps/api via uv.
API := apps/api

.PHONY: help install dev db up down test lint typecheck contracts check migrate revision worker worker-loop web-install web-dev web-build web-test

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install backend deps into apps/api/.venv
	cd $(API) && uv sync --extra dev

dev: ## Run the API with autoreload (needs db up)
	cd $(API) && uv run uvicorn juggle.main:app --reload --port 8000

db: ## Start only Postgres/PostGIS
	docker compose up -d db

up: ## Start the full stack (db + api)
	docker compose up --build

down: ## Stop the stack
	docker compose down

test: ## Run backend tests
	cd $(API) && uv run pytest -q

lint: ## Ruff lint
	cd $(API) && uv run ruff check .

typecheck: ## mypy strict
	cd $(API) && uv run mypy

contracts: ## Enforce module boundaries (import-linter)
	cd $(API) && uv run lint-imports

check: lint typecheck contracts test ## Everything CI runs

migrate: ## Apply migrations
	cd $(API) && uv run alembic upgrade head

seed: ## Seed the local DB with demo marketplace data
	cd $(API) && uv run python scripts/seed_demo.py

worker: ## Run one maintenance tick (waitlist sweep, hold reclaim, reminders)
	cd $(API) && uv run python -m juggle.worker

worker-loop: ## Run the maintenance worker continuously (every 5 min)
	cd $(API) && uv run python -m juggle.worker --loop

web-install: ## Install frontend deps
	cd apps/web && npm install

web-dev: ## Run the Quasar dev server (proxies /api to :8000)
	cd apps/web && npm run dev

web-build: ## Typecheck + build the frontend
	cd apps/web && npm run build

web-test: ## Run the frontend unit tests (Vitest)
	cd apps/web && npm run test

revision: ## Autogenerate a migration: make revision m="add sessions"
	cd $(API) && uv run alembic revision --autogenerate -m "$(m)"
