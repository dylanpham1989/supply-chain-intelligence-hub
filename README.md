# Supply Chain Intelligence Hub

Multi-tenant platform that turns shipping manifests, invoices and supplier contracts into
queryable insights. Logistics and manufacturing companies sign up as separate tenants, upload
documents, and ask questions in plain language against their own data.

> Status: in progress. Phases 1 and 2 are complete (foundation, schema, tenant isolation).
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
make migrate
make seed
```

| Service | URL |
|---------|-----|
| API docs | http://localhost:8000/docs |
| Web | http://localhost:5173 |
| MinIO console | http://localhost:9001 |
| Postgres | localhost:55432 |
| Redis | localhost:56379 |

Postgres and Redis are published on 55432 and 56379 rather than their default ports, because a native instance on the machine takes the loopback address first and host tooling would then talk to the wrong database.

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
make up-obs      # add prometheus (:9090) and grafana (:3001)
```

Logs are JSON on stdout, every line carrying the request id, tenant and user. The same id
follows an upload into the worker, so one grep covers the whole chain. `/metrics` exposes
Prometheus counters with deliberately bounded labels, and `/health/live` and `/health/ready`
are split so that a slow database cannot get every pod restarted. The reasoning is in
[docs/observability.md](docs/observability.md), and the test strategy is in
[docs/testing.md](docs/testing.md).

Configuration lives in one place, `backend/app/core/config.py`. Nothing else reads the
environment directly. Any environment other than `local` or `test` refuses to start while the
placeholder secrets from `.env.example` are still in use.

## Tenant isolation

Tenants share one schema and every owned row carries a `tenant_id`. That scales better than a
database or schema per tenant, at the cost of being the option where a forgotten `WHERE` leaks
data, so the boundary is enforced in three places:

1. Postgres row-level security. Each tenant table has a policy keyed on the `app.tenant_id`
   setting, enabled with FORCE so it applies to the table owner too. The setting is written with
   `set_config(..., is_local => true)`, which ties it to the transaction and keeps a pooled
   connection from carrying one tenant's id into the next request. An unset setting resolves to
   NULL, which matches nothing, so a request that forgets to scope itself reads zero rows rather
   than everything.
2. The repository layer takes `tenant_id` in its constructor and filters on it, which also keeps
   query plans on the composite indexes that lead with `tenant_id`.
3. The application connects as a role created `NOSUPERUSER NOBYPASSRLS`, so the policies cannot
   be sidestepped.

`backend/tests/integration/test_rls.py` covers reads, writes, updates, deletes, aggregates and
the repository layer, and asserts on `pg_class` that no tenant table is missing a policy. The
policies were mutation tested, including a permissive `USING (true)` variant, to confirm the
tests fail when the boundary is removed.

## Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Project foundation, local stack, health checks | Done |
| 2 | Schema and tenant isolation with row-level security | Done |
| 3 | JWT auth with refresh rotation, role-based access | Done |
| 4 | Core REST API, filtering, Redis caching | Done |
| 5 | Document upload and background ingestion | Done |
| 6 | Retrieval pipeline, vector store, grounded answers | Done |
| 7 | Dashboard, tables, charts, question answering UI | Done |
| 8 | Shipment risk classification | Dropped, see docs/PROGRESS.md |
| 9 | Structured logging, metrics, full test suite | Done |
| 10 | Kubernetes manifests, CI/CD, Terraform modules | Next |
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
