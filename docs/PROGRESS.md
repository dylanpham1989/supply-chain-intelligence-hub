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
