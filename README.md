# Supply Chain Intelligence Hub

Multi-tenant platform that turns shipping manifests, invoices and supplier contracts into
queryable insights. Logistics and manufacturing companies sign up as separate tenants, upload
documents, and ask questions in plain language against their own data.

> Status: in progress. Phase 1 of 11 is complete (project foundation and local stack).
> The roadmap below tracks what is built and what is not, so nothing here overstates the
> current state.

## What this project is for

A single system that exercises fullstack development, AI engineering and infrastructure work,
rather than three separate demos. The design goals, in order:

1. `make up` brings the whole stack online with no API keys and no cloud account.
2. Every technical choice has a written reason, so it can be defended or revisited.
3. Claims about isolation, performance and quality are backed by tests and measurements.

## Stack

| Layer | Choice |
|-------|--------|
| Frontend | React 19, TypeScript (strict), Vite, Tailwind |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 async, Pydantic v2 |
| Data | PostgreSQL 16 with pgvector, Redis 7, S3 (MinIO locally) |
| AI | sentence-transformers embeddings, hybrid retrieval, pluggable LLM provider |
| Jobs | ARQ workers on Redis |
| Infrastructure | Docker, Kubernetes via Kustomize, Terraform, GitHub Actions |

## Quick start

Requires Docker with at least 6 GB of memory available.

```bash
git clone https://github.com/dylanpham1989/supply-chain-intelligence-hub.git
cd supply-chain-intelligence-hub
make up
```

| Service | URL |
|---------|-----|
| API docs | http://localhost:8000/docs |
| Web | http://localhost:5173 |
| MinIO console | http://localhost:9001 |

`make help` lists every target. `make verify` runs what CI runs: lint, type check, tests and
the repository audit.

## Working on it locally

```bash
make install     # uv sync for the backend, npm ci for the frontend
make test        # pytest and vitest
make lint        # ruff and oxlint
make typecheck   # mypy (strict) and tsc
make verify      # all of the above
make down        # stop, keeping data volumes
make clean       # stop and delete data volumes
```

Configuration lives in one place, `backend/app/core/config.py`. Nothing else reads the
environment directly. Any environment other than `local` or `test` refuses to start while the
placeholder secrets from `.env.example` are still in use.

## Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Project foundation, local stack, health checks | Done |
| 2 | Schema and tenant isolation with row-level security | Next |
| 3 | JWT auth with refresh rotation, role-based access | Planned |
| 4 | Core REST API, filtering, Redis caching | Planned |
| 5 | Document upload and background ingestion | Planned |
| 6 | Retrieval pipeline, vector store, grounded answers | Planned |
| 7 | Dashboard, tables, charts, question answering UI | Planned |
| 8 | Shipment risk classification | Planned, may be dropped |
| 9 | Structured logging, metrics, full test suite | Planned |
| 10 | Kubernetes manifests, CI/CD, Terraform modules | Planned |
| 11 | Architecture docs, decision records, demo | Planned |

## Repository layout

```
backend/     FastAPI application, AI package, worker, migrations, tests
frontend/    React application
infra/       Dockerfiles, Kubernetes manifests, Terraform modules
scripts/     Repository and data utilities
data/        Sample documents used by the demo
docs/        Architecture, decisions, runbooks
```

## License

MIT. See [LICENSE](LICENSE).
