SHELL := /bin/bash
COMPOSE := docker compose
BACKEND := cd backend &&
UVR := $(BACKEND) uv run

.DEFAULT_GOAL := help
.PHONY: help up down restart logs ps build shell-api shell-db seed migrate \
        test test-cov lint fmt typecheck verify audit clean install

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

.env:
	@cp .env.example .env
	@echo "created .env from .env.example"

up: .env ## Start the full local stack
	$(COMPOSE) up -d --build
	@echo "api  http://localhost:8000/docs"
	@echo "web  http://localhost:5173"

down: ## Stop the stack, keep volumes
	$(COMPOSE) down

restart: down up ## Restart the stack

logs: ## Follow logs for all services
	$(COMPOSE) logs -f --tail=100

ps: ## Show service status
	$(COMPOSE) ps

build: ## Rebuild images without starting
	$(COMPOSE) build

shell-api: ## Shell inside the api container
	$(COMPOSE) exec api bash

shell-db: ## psql inside the postgres container
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-postgres} -d $${POSTGRES_DB:-scih}

install: ## Install backend and frontend dependencies locally
	$(BACKEND) uv sync
	cd frontend && npm ci

migrate: ## Apply database migrations
	$(COMPOSE) exec -T api alembic upgrade head

migrate-down: ## Roll back one migration
	$(COMPOSE) exec -T api alembic downgrade -1

revision: ## Autogenerate a migration, name it with m="..."
	$(COMPOSE) exec -T api alembic revision --autogenerate -m "$(m)"

seed: ## Load demo tenants and shipments
	$(COMPOSE) exec -T api python -m scripts.seed_data

test: ## Run backend and frontend tests
	$(UVR) pytest
	cd frontend && npm run test -- --run

test-cov: ## Run backend tests with coverage report
	$(UVR) pytest --cov --cov-report=term-missing --cov-report=html

lint: ## Lint backend and frontend
	$(BACKEND) uv run ruff check .
	$(BACKEND) uv run ruff format --check .
	cd frontend && npm run lint

fmt: ## Format backend and frontend
	$(BACKEND) uv run ruff format .
	$(BACKEND) uv run ruff check . --fix
	cd frontend && npm run format

typecheck: ## Type-check backend and frontend
	$(BACKEND) uv run mypy app
	cd frontend && npm run typecheck

audit: ## Check for assistant tooling traces
	bash scripts/check_ai_traces.sh

verify: lint typecheck test audit ## Everything CI runs

clean: ## Stop the stack and delete volumes
	$(COMPOSE) down -v
	rm -rf backend/.pytest_cache backend/.ruff_cache backend/.mypy_cache backend/htmlcov
	rm -rf frontend/dist frontend/node_modules/.vite
