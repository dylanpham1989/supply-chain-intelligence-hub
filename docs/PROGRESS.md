# Progress Log

Short running notes so that work can be picked up without re-reading the diff.

## 2026-09-22 - Phase 1, project foundation

Done:
- Repository initialised. `.gitignore` covers assistant tooling, secrets, build output and
  Terraform state, and landed as the first commit so nothing leaks into history.
- `scripts/check_ai_traces.sh` checks tracked contents, tracked paths, paths that ever existed
  in history, and commit metadata. Verified against three deliberate violations before use.
  Wired into pre-commit; it will also run in CI in phase 10.
- Backend project set up with uv, Python 3.12 pinned. ruff (with the bandit rules), mypy in
  strict mode, pytest with a 70 percent coverage floor.
- `app/core/config.py` is the only place that reads the environment. Added a validator that
  refuses to start a staging or prod process while the placeholder JWT or S3 secret is in use,
  with tests covering both directions.
- `app/core/logging.py` sets up structlog with a redaction processor for anything that looks
  like a credential. Console renderer locally, JSON elsewhere. uvicorn access log disabled
  because phase 9 adds one access line per request.
- `/health` probes Postgres and Redis concurrently with a 2 second timeout each, and answers
  503 when either is down rather than raising.
- Multi-stage Dockerfiles for api and web. Dependencies install in their own layer, the
  virtualenv lives at `/opt/venv` so the development bind mount does not shadow it, and the
  runtime stage runs as uid 10001.
- docker compose stack: pgvector/pg16, redis, minio, api, web. Every dependency has a
  healthcheck and the api waits on `service_healthy`, not `service_started`.
- `init-db.sql` creates the vector and pgcrypto extensions plus an `app_user` role with
  NOBYPASSRLS, ready for the row-level security work in phase 2.
- Frontend scaffolded with Vite. Enabled `strict`, `noUncheckedIndexedAccess` and
  `exactOptionalPropertyTypes`, which the template leaves off, and added `tests` to the
  type-checked project. App shows live status for api, database and redis.

Deviations from the plan, with reasons:
- No worker container yet. `Dockerfile.worker` and the compose service arrive in phase 5 with
  the code they run. A container that crash-loops from day one is worse than one added later.
- Kept `oxlint` from the Vite template instead of adding eslint. It needs no configuration and
  is much faster; eslint can replace it if a plugin is ever needed.
- Dropped `manualChunks` from the Vite build. Vite 8 rejects the object form, and there is
  nothing worth splitting until charts arrive in phase 7.

Verified:
- `ruff check`, `ruff format --check`, `mypy app` clean. 10 backend tests pass.
- `tsc -b`, `oxlint`, `prettier --check` clean. 3 frontend tests pass. Bundle 69 kB gzipped.

Next: phase 2, domain models and tenant isolation. Start with `init-db.sql` roles, then the
`TenantRepository` base and the row-level security migration.

### Review pass and what running it actually caught

Four bugs only appeared once the stack was running, which is the argument for verifying in
containers rather than trusting unit tests:

1. `CORS_ORIGINS=http://localhost:5173` crashed the api on boot. pydantic-settings JSON-decodes
   complex types in the env source before any validator runs, so a comma-separated list is
   invalid. Fixed with `Annotated[list[str], NoDecode]` plus a validator that accepts both the
   comma form and a JSON array, since compose files use the first and Kubernetes the second.
   Added tests that go through the env source, not just the constructor, because the original
   test passed the value directly and therefore never exercised the failing path.
2. The web container showed "API unreachable" while the api was healthy. The Vite dev proxy
   pointed at `localhost:8000`, and inside that container localhost is the web container.
   Added `VITE_API_PROXY=http://api:8000` to the compose service.
3. `npm ci` failed in the image because the lockfile still carried the scaffolded package name
   and version after package.json was rewritten. Regenerated the lockfile, and moved the build
   to node:24-alpine so the container npm matches the local one.
4. The production web image had no route to the api at all, so the built bundle could never
   reach `/health`. Replaced the static nginx config with an nginx template, since nginx:alpine
   runs envsubst over `/etc/nginx/templates` at startup. `NGINX_ENVSUBST_FILTER=API_UPSTREAM`
   is required, otherwise envsubst also eats nginx's own `$host`, `$uri` and
   `$proxy_add_x_forwarded_for` and the result proxies nowhere.

Changes from reviewing the code rather than running it:

5. OpenAPI and Swagger UI were served in every environment. They now only appear in local, test
   and staging, since the schema describes the whole attack surface. Tests cover both cases.
6. The api container healthcheck hit `/openapi.json`, which finding 5 removes in prod, and
   `/health` answers 503 when a dependency is down. A liveness check should only report whether
   the process still answers, so it now treats an HTTP error response as alive. A dependency
   being down is a readiness concern and must not restart the container.

Measured after the fixes:
- 14 backend tests, 98 percent coverage. 3 frontend tests. Everything in `make verify` green.
- api image 706 MB, production web image 76 MB, frontend bundle 69 kB gzipped.
- `make up` from warm cache to all four services healthy: about 40 seconds.
- Stopping Postgres returns 503 with `db: false` and logs a warning. Restarting it recovers
  with no api restart.

## 2026-09-22 - Phase 2, schema and tenant isolation

Nine tables, two migrations, and the tests that back the isolation claim.

Shape of it:
- `TenantEntity` carries the uuid v7 primary key, timestamps and `tenant_id` so the eight
  tenant-owned tables do not repeat themselves. `tenants` itself is not tenant-scoped.
- `TenantRepository[ModelT]` takes `tenant_id` in the constructor, so a repository with no
  tenant cannot be constructed. It repeats the tenant filter in the query even though RLS
  already applies, which keeps the planner on the tenant-leading indexes.
- Migration 0002 enables, forces and policies every table in `TENANT_SCOPED_TABLES`, reading
  that tuple from the models package. Adding a model to the tuple is what turns its policy on.
- Seed data is deterministic: 2 tenants, 240 shipments over 13 months, 76 and 80 percent
  on-time, plus contracts and alerts. Same numbers every run, so screenshots and the demo
  script stay accurate.

Four things the first autogenerated migration got wrong:
1. Postgres enum labels came out as `LATE_DELIVERY` because SQLAlchemy stores the member name,
   not the value. The analytics queries in phase 4 filter on `status = 'delayed'` in raw SQL and
   would have silently matched nothing. Added a `pg_enum` helper with `values_callable`.
2. `index=True` on the `tenant_id` mixin created a redundant single-column index on all eight
   tables. Postgres already uses the leading column of a composite, so those were write
   overhead for nothing. Dropped them and gave `alerts` a plain `(tenant_id, created_at)`,
   since it only had a partial index for the unread badge.
3. `pgvector.sqlalchemy.vector.VECTOR` was emitted without the matching import.
4. No `CREATE EXTENSION`. `init-db.sql` only runs on a fresh volume, so migrating an existing
   database would have failed on the vector column.

Also: dropping a table leaves its enum type behind, so `downgrade base` followed by
`upgrade head` failed with "type already exists" until the downgrade dropped the types too.

A port conflict worth recording. A native postgres and a native redis on this machine hold
127.0.0.1:5432 and :6379. Docker binds 0.0.0.0 but loses the loopback address, so anything
run from the host was talking to those instead of the containers, while the api container was
fine because it resolves `postgres` over the compose network. Health checks were green the
whole time. Published ports are now 55432 and 56379, and migrations run inside the container.

Mutation tested the policies rather than trusting green tests:
- Drop the policy on `shipments`: 8 tests fail.
- Restore it without FORCE: only the pg_class assertion fails, which is correct, since FORCE
  only affects the table owner and the tests connect as app_user.
- Policy with no WITH CHECK: everything still passes, and that is right. Postgres uses USING
  for the write side when WITH CHECK is absent, so the clause is redundant. Kept it explicit.
- Policy as `USING (true) WITH CHECK (true)`: 6 tests fail, including the insert one. That is
  the mutation that proves the insert test is live, because dropping the policy entirely makes
  the table default-deny and the insert test would pass for the wrong reason.

Measured:
- 30 backend tests, 93 percent coverage. `app/db/rls.py` and `app/repositories/base.py` at 100.
  `app/db/session.py` is at 0 because nothing depends on it until the auth work lands.
- `EXPLAIN ANALYZE` on a tenant-scoped shipment read: `Index Scan Backward using
  ix_shipments_tenant_created`, and the policy predicate resolves to a One-Time Filter rather
  than a per-row check, so RLS costs essentially nothing here.
- `alembic downgrade base` then `upgrade head` is clean.

Next: phase 3, auth. The dependency that resolves the token has to share one session with the
one that sets the tenant context, otherwise the context lands on a connection nobody queries.

### Review pass on phase 2

Four findings, two of them real bugs.

1. **Two engines in one process.** `app/main.py` built its own engine in the lifespan while
   `app/db/session.py` built another at import. That is two connection pools, and `/health`
   was probing the one that no request would ever use. The engine now lives in
   `db/session.py` alone and the lifespan disposes it.
2. **Migration 0002 imported `TENANT_SCOPED_TABLES` from `app.models`.** A migration has to
   keep describing the schema as it was at that revision, and this one read a list that later
   phases will grow. Reproduced it by adding a name to the tuple: `alembic downgrade base`
   fails on `ALTER TABLE future_phase_table NO FORCE ROW LEVEL SECURITY`. The list is now
   spelled out in the migration, and `tests/unit/test_migrations.py` fails if it drifts from
   the models, in either direction. That last part matters: the reverse mistake, a new model
   with a `tenant_id` that nobody adds to the list, is a silent leak rather than an error.
3. `.env.example` advertised `DATABASE_URL_HOST` and friends that nothing reads. Replaced with
   a comment about where the host defaults actually come from.
4. `poolclass=None` in the test engine means "use the default pool", not "no pool". With an
   engine built per test that leaves connections around, so it is `NullPool` now.

After: 34 backend tests, 95 percent coverage, one engine, one `app_user` connection at idle.
`db/session.py` sits at 46 percent because `get_session` has no caller until the auth work.
