SHELL := /bin/bash
COMPOSE := docker compose
COMPOSE_OBS := docker compose -f docker-compose.yml -f docker-compose.observability.yml
BACKEND := cd backend &&
UVR := $(BACKEND) uv run

.DEFAULT_GOAL := help
.PHONY: help up up-obs down down-obs restart logs ps build shell-api shell-db seed \
        migrate migrate-down revision test test-unit test-cov lint fmt typecheck \
        verify audit clean install kind-up kind-deploy kind-down smoke tf-validate

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

up-obs: .env ## Start the stack with Prometheus and Grafana
	$(COMPOSE_OBS) --profile observability up -d
	@echo "prometheus http://localhost:9090"
	@echo "grafana    http://localhost:3001"

down: ## Stop the stack, keep volumes
	$(COMPOSE) down

down-obs: ## Stop Prometheus and Grafana, leave the stack running
	$(COMPOSE_OBS) --profile observability stop prometheus grafana

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
	# --all-groups so that mypy sees the optional providers. Without them it
	# treats the anthropic and openai imports as Any and reports nothing, while
	# CI installs them and fails.
	$(BACKEND) uv sync --all-groups
	cd frontend && npm ci

migrate: ## Apply database migrations
	$(COMPOSE) exec -T api alembic upgrade head

migrate-down: ## Roll back one migration
	$(COMPOSE) exec -T api alembic downgrade -1

revision: ## Autogenerate a migration, name it with m="..."
	$(COMPOSE) exec -T api alembic revision --autogenerate -m "$(m)"

seed: ## Load demo tenants and shipments
	$(COMPOSE) exec -T api python -m scripts.seed_data

test: ## Run backend and frontend tests (needs `make up`)
	$(UVR) pytest
	cd frontend && npm run test -- --run

test-unit: ## Run only the tests that need no services
	$(UVR) pytest -m "not integration"

test-cov: ## Run backend tests with coverage and the per-module floors
	$(UVR) pytest --cov --cov-report=term-missing --cov-report=html --cov-report=json
	$(UVR) python scripts/check_critical_coverage.py

lint: ## Lint backend and frontend
	$(BACKEND) uv run ruff check .
	$(BACKEND) uv run ruff format --check .
	cd frontend && npm run lint

fmt: ## Format backend and frontend
	$(BACKEND) uv run ruff format .
	$(BACKEND) uv run ruff check . --fix
	cd frontend && npm run format

typecheck: ## Type-check backend and frontend
	$(BACKEND) uv run mypy app ai worker
	cd frontend && npm run typecheck

audit: ## Check for assistant tooling traces
	bash scripts/check_ai_traces.sh

verify: lint typecheck test audit ## Everything CI runs

smoke: ## Drive the running stack end to end (upload, index, ask)
	bash scripts/smoke_test.sh

kind-up: ## Create the local kubernetes cluster with ingress and metrics-server
	bash scripts/kind-up.sh

kind-deploy: ## Build, load and apply the local overlay, then seed
	bash scripts/kind-deploy.sh

kind-down: ## Delete the local kubernetes cluster
	kind delete cluster --name scih

tf-validate: ## Format check, init and validate the terraform environments
	cd infra/terraform && terraform fmt -check -recursive
	cd infra/terraform/envs/staging && terraform init -backend=false -input=false >/dev/null && terraform validate

clean: ## Stop the stack and delete volumes
	$(COMPOSE) down -v
	rm -rf backend/.pytest_cache backend/.ruff_cache backend/.mypy_cache backend/htmlcov
	rm -rf frontend/dist frontend/node_modules/.vite
