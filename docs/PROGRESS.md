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

## 2026-09-22 - Phase 3, auth and access control

Signup, login, refresh rotation, permission guards, rate limiting, and the wiring that makes
the phase 2 policies apply to a real request.

Shape of it:
- Access tokens live 15 minutes and carry a `typ` claim. Without it a refresh token, which
  lives a week, would be accepted as a bearer.
- Refresh tokens are stored as a sha256 digest, never in the clear, and rotate on use.
  Presenting an already revoked token means a copy is loose, so the whole family is revoked
  rather than that one token. The honest holder gets logged out too; that is the trade.
- Endpoints ask for a permission, never for a role. `require("user:write")` reads a map keyed
  on role, so a new role is one entry rather than an edit to every route.
- Login is rate limited per tenant, email and IP, and pays the bcrypt cost even when the
  workspace or the email does not exist, so a miss cannot be told from a wrong password by
  timing. Both answers are byte for byte identical.
- bcrypt runs in a worker thread. At cost 12 it is a couple hundred milliseconds of CPU, which
  on the event loop would stall every other request on the worker.

The wiring that matters: `get_current_user` reads the tenant off the verified token and sets
it on the session, and FastAPI hands the route handler that same session object. If those were
two sessions, the context would land on a connection nobody queries and every policy would see
no tenant. `tests/integration/test_request_scoping.py` exists for that one thing.

Five mutations, and the fifth found a hole:
1. Remove `set_tenant_context` from the dependency: 3 tests fail. They fail with 401 rather
   than leaking, because an unset tenant makes the user lookup itself return nothing.
2. Set the context on a different session: same 3 tests fail.
3. Drop the policy on `shipments` (phase 2): 8 tests fail.
4. Permissive `USING (true)` policy: 6 tests fail.
5. Read the tenant from an `X-Tenant-Id` header instead of the token: **all 33 tests passed**.
   Nothing sent that header, so the single most damaging mistake in a multi-tenant API went
   unnoticed. Added tests that try to steer the tenant through a header, a query parameter and
   a request body; the header one now fails under that mutation.

Bugs found while building:
- `EmailStr` rejects `.test`, which RFC 6761 reserves for exactly this. The demo seed uses
  `admin@acme.test`, so every seeded account was unable to log in. Replaced it with a type that
  validates syntax and normalises case but accepts reserved and internal domains. Whether an
  address receives mail is not a question syntax can answer; a verification email is.
- `UserService.list` returned `Page[User]` with `User` being the ORM model, which pydantic
  cannot build a schema for. The service returns rows and a count now, and the router builds
  the envelope. Better separation anyway.
- **Coverage was being measured wrong across the whole project.** SQLAlchemy's async layer runs
  awaits inside greenlets, and coverage.py does not trace those by default, so every line
  reached through a database call was reported as uncovered. `auth_service.py` showed 61 while
  its tests clearly exercised it. With `concurrency = ["greenlet", "thread"]` the same suite
  reports 91 for that file and 94 overall.

Known issue, not fixed: passlib warns that `crypt` is removed in Python 3.13. We pin 3.12 so it
runs, but passlib is unmaintained and the way out is `pwdlib` with argon2. Left visible rather
than silenced.

Measured: 104 backend tests, 94 percent coverage. `permissions.py`, `db/rls.py`,
`repositories/base.py` and both v1 routers at 100, `security.py` at 98, `auth_service.py` at 91.

Environment note: `docker compose build` hangs on this machine through buildx bake, and plain
`docker build` works but one wheel took 596 seconds to download. The api image is stale as a
result; the tests run against the source on the host, so this blocked nothing.

Next: phase 4, the shipment and analytics endpoints, with the cache key namespaced per tenant.

## 2026-09-22 - build caching and a review pass

Build caching:
- Both Dockerfiles mount a dependency cache (`/root/.cache/uv`, `/root/.npm`). A cache mount
  survives layer invalidation, so changing one dependency downloads one wheel instead of all
  of them. On a link where pypi is serving at 20 kB/s that is the difference between a minute
  and half an hour, and it matters more once torch arrives.
- `Dockerfile.api` takes a `UV_DEFAULT_INDEX` build arg, empty by default, for building
  through a mirror without that mirror being baked into the repository.

A misdiagnosis, corrected. `docker compose build` looked like it hung and plain `docker build
--progress=plain` looked like it worked, so the conclusion was that buildx bake was broken
here. It was not. The default progress renderer shows nothing until a step finishes, and the
step was a 15 minute download. Compose builds fine. The `COMPOSE_BAKE=false` line written on
that basis was removed rather than shipped; a workaround for a problem that was never there is
worse than nothing, because the next person believes it.

For the record on the slow link, since it cost real time: the host itself, not docker, pulls
from files.pythonhosted.org at 17 to 21 kB/s across repeated tries, while Cloudflare gives
1.8 MB/s and the npm registry 1.4 MB/s on the same connection. The Fastly response names the
Singapore edge with an age of six days, so it is a cache hit being served slowly, not a cold
origin. That is peering between this ISP and Fastly, and nothing local fixes it.

Review findings:
1. **Three different error shapes.** Our handler answered `{code, message}`, validation
   failures answered `{detail: [...]}` and an unknown route answered `{detail: "Not Found"}`.
   A client had to branch on which one it got. Handlers for `RequestValidationError` and
   `StarletteHTTPException` now map into the same envelope, validation failures name the
   offending fields, and a catch-all logs the traceback and returns `internal_error` without
   it. A test asserts no error body contains a traceback or a source path.
2. **`refresh_tokens` grew forever.** Every login and every rotation inserted a row and nothing
   removed any. Login now prunes that user's expired and revoked tokens, which bounds the table
   without a scheduler: a user cannot hold more rows than they have live sessions.

The pruning test failed first time and the test was wrong, not the code: login prunes one row
and inserts one, so the row count does not move. Counting spent rows instead states the actual
invariant. Both fixes were mutation tested; disabling pruning fails its test, and swapping the
HTTP exception handler fails two envelope tests.

111 backend tests, 94 percent coverage.

## 2026-09-22 - Phase 4, shipments, suppliers, alerts and analytics

22 endpoints. Listing with filters, sorting and paging; five analytics aggregates; a
tenant-namespaced cache in front of the dashboard.

Shape of it:
- Aggregates run in SQL. `FILTER (WHERE ...)` for the counts, `generate_series` left joined
  against shipments so a quiet month is a zero rather than a gap the chart closes up, and
  `NULLIF(..., 0)` so an empty window is null instead of a division error.
- Sort columns come from a dict, never `getattr(Model, user_input)`. The schema types them as
  `Literal`, so an unknown column is a 422 rather than a 500 or, worse, an ordering by a column
  the caller should not be able to read.
- Every list orders by the sort column and then the primary key. Without the tie-break, paging
  over duplicate values repeats and skips rows.
- Cache keys start with the tenant. Row-level security does not reach into redis, so a key that
  omits the tenant serves one customer's dashboard to another and nothing downstream notices.
  Writes invalidate by tag through a redis set, not `KEYS`, which blocks the server while it
  scans. Reads and writes both fail open. `X-Cache` says hit or miss so the cache is observable
  without a debug endpoint.

Two bugs that only appeared when the endpoints were actually called:
1. **Every request to a list endpoint returned 422.** FastAPI flattens one pydantic query model
   per endpoint. A second one is not an error: both quietly become query parameters named after
   the argument, so `filters` and `pagination` were required scalars. Reproduced it in six lines
   against a bare app. Filter models now inherit `PaginationParams`, one model per endpoint, and
   a test reads the OpenAPI schema and fails if any query parameter is named after a model.
2. **The timeseries endpoint returned 500.** `:since::timestamptz` inside `text()` confuses the
   bind parameter parser, since `::` is also postgres cast syntax. `CAST(:since AS timestamptz)`
   is unambiguous. Nothing caught it because no test called the endpoint; there are now
   parametrised tests over all five, on an empty workspace and on one with rows.

Cache mutations, all caught:
- Drop the tenant from the key: 7 tests fail, including the cross-tenant leak.
- Drop the params from the key: 3 fail, including two windows sharing one entry.
- Stop invalidating on write: 2 fail.

Measured: 162 backend tests, 94.5 percent coverage. Against the seeded data, acme reports 120
shipments at 76.1 percent on time and globex 120 at 80.5, from separate cache entries.

Next: phase 5, document upload and the ingestion worker.

## 2026-09-23 - Phase 5, document upload and the ingestion worker

Upload returns 202 and hands the file to an ARQ worker. Parsing a contract takes seconds,
which is longer than a proxy will hold a connection, and a failed request would lose the
upload entirely.

Shape of it:
- The object key is server generated, `{tenant_id}/{document_id}.pdf`. The client's filename
  is kept only as a label. A filename that reaches the object store is a path traversal waiting
  to be tried.
- Uploads are validated on what they are, not what they claim: a pdf has to start with `%PDF-`,
  a csv has to parse as one, and the read is capped as it streams rather than after.
- The job is idempotent. Chunks are deleted before they are written and manifest rows are
  deduplicated on reference, so a redelivered message replaces its output instead of doubling
  it. Redis delivers at least once; the job has to be safe to repeat.
- `PermanentError` and `TransientError` are separate. A scanned pdf will still be scanned on
  the next attempt, so it fails once with a message a user can read rather than retrying three
  times and giving up silently.
- Manifest rows become shipments. Structured data belongs in the table it describes: counting
  late deliveries in sql is exact, and asking an index the same question is not. One summary
  chunk keeps the file findable by a question.
- `worker/db.py` is the only route from a job to the database, because a job has no request to
  carry the tenant and has to set the context itself.

Two bugs the suite would not have found:
1. **Ingesting a manifest left the dashboard stale.** The worker wrote 42 shipments and the
   summary endpoint kept serving 120 from cache. Cache invalidation existed on the api write
   path and not on the worker's. A job writing shipments is as much a write as a request is.
   Found by uploading through the running stack and comparing the endpoint against the table:
   162 rows in postgres, 120 in the response.
2. **The cleaner was dead code.** `clean_pages` was written, tested by nothing, and never
   called, so repeated headers and footers went into every chunk. Coverage reporting it at
   0 percent is what gave it away, which is the argument for measuring `ai` and `worker` rather
   than only `app`.

A chunking bug found while checking the samples by hand: the clause regex matched any line
starting with a number, so the wrapped body line "2 percent of the shipment value ..." read as
clause 2 and cut clause 4.2 in half, dropping the figure a question about penalties is looking
for. Requiring an uppercase letter after the number, plus a length cap on the heading line,
fixes it. Clause 4.2 now survives whole at 411 characters with both percentages intact, and a
test pins the exact text.

Sample documents are committed: two contracts, an invoice with a line item table, and two
manifests whose headers are deliberately awkward (Ref No, POL, POD, Cartons, Invoice Value)
with a few malformed rows, because real manifests always have some. A demo that starts with
"first find yourself a shipping contract" is a demo nobody runs.

On the slow link: pypi stalled completely, 18 minutes with no bytes moved. The Aliyun mirror
served the same wheels at 1.09 MB/s and the install finished in 41 seconds. It resolved a
lockfile with 786 mirror URLs baked in, which would have pointed every clone at a mirror, so
the lock was restored from git and only the new packages resolved against pypi. The mirror is
passed as a build arg and an env var, never committed.

209 backend tests, 92 percent coverage.

Next: phase 6, embeddings and retrieval.

## 2026-09-23 - Phase 6, retrieval and grounded answers

Ask a question, get an answer that cites the chunk it came from.

Shape of it:
- Embeddings from all-MiniLM-L6-v2, 384 dimensions, cpu, about 80 MB. Loaded once at worker
  startup and run in a thread, because sentence-transformers is synchronous and would otherwise
  hold the event loop for every other job.
- Retrieval is hybrid. Vector search alone blurs exact strings like INV-2026-0412 or clause
  4.2; keyword search alone misses a question phrased differently from the document. The two
  result lists are merged with reciprocal rank fusion, which uses positions rather than scores,
  because cosine runs 0 to 1 and ts_rank_cd has no upper bound and adding them means inventing
  a conversion.
- HNSW rather than IVFFlat. IVFFlat trains its lists on existing rows and a migration always
  runs against an empty table, so it would build on nothing and report nothing wrong.
- Aggregate questions go to sql. Retrieval returns the top k, so "how many shipments were late"
  answered from an index is a guess with a number on it. The model proposes a json filter and
  never sql; the filter is validated against a schema that forbids unknown keys, so the worst a
  bad generation achieves is a validation failure. Regions are expanded in code, because asked
  to list the EU a model produces a plausible subset and leaves a few members out.
- The default provider is a mock that answers by extraction with no network call. CI and a
  fresh clone run the whole pipeline with no key, and it separates two failures that look
  identical from outside: bad retrieval and bad generation.

The isolation tests were nearly worthless and the mutation testing is what showed it. Deleting
the tenant predicate from both search statements left all ten passing, because the row-level
security policy caught it. That is defence in depth working, and it also meant the tests said
nothing about the statements. Two tests now scope the session to one tenant and ask the store
for another: with the predicate they intersect to nothing, without it the other tenant's rows
come back. Those two fail under the mutation; the other ten still pass, which is the right
outcome for both layers.

Worth recording for pinecone, which has no policy behind it: there the query filter is the only
boundary, so testing it separately is not academic.

Three bugs from the review:
1. `Dockerfile.api` used `--no-dev`, which only drops the dev group. Adding ingest and ai to
   the default groups for local work meant the api image was about to gain torch and pandas.
   `--no-default-groups` is what was meant.
2. torch resolves to the cuda build unless told otherwise, and the worker build was pulling
   nvidia-cublas at 517 MB into a container with no gpu. 43 nvidia packages in the lock, now
   zero. `tool.uv.sources` only reaches direct dependencies, so torch had to be declared
   directly to point it at the cpu index.
3. The embedder protocol was referenced by nothing, so it documented nothing. Coverage reported
   it at 0 percent, which is how it surfaced.

A bug found by running it: asyncpg infers parameter types from the statement, and a bare
`:param` compared against NULL gives it nothing to infer from, so an unfiltered search failed
with "could not determine data type of parameter $3". Every optional parameter is cast now.

A fourth, found by reading `docker history` rather than trusting the total: the layer that
copies the source was 1.36 GB. A `.dockerignore` pattern without a glob is anchored to the
root, so `backend/.venv` was never excluded and both images carried a copy of the local
virtualenv alongside the one the build had just made. 1.2 GB of it in the worker, 206 MB in the
api, and it had been there since phase 1. The api image drops from 723 MB to 419 MB.

Sizes after that: api 419 MB with no torch in it, worker venv 1.5 GB of which torch is 652 MB,
plus 88 MB for the baked-in model. That is the cost of embedding locally; a hosted embedding
api trades the gigabytes for a key and a network dependency.

Three more the tests did not catch, all found by running the stack and reading what came back:

4. **The embedding job was never written.** The commit claimed it and shipped the placeholder;
   the replacement had missed its anchor after a reformat and nothing checked. Ingest reported
   success, chunks existed, no vectors, retrieval returned nothing, and no error anywhere. Two
   tests now assert vectors are written and that a repeat run finds nothing left to do.
5. **The api had no embedding model.** Answering a question embeds the question, on the read
   path, in the api process, so `/ask` returned 500. Keeping torch out of that image was wrong
   because the read path had not been traced before optimising it. The api carries the ai group
   now; keeping it small would mean a separate embedding service or an onnx build of the same
   model, and neither is worth the moving parts here.
6. **Structured questions answered with the wrong number.** The offline mock returns no json,
   so the filter fell back to empty and "how many shipments were delayed" came back with the
   count of everything. That is worse than an error because it looks like an answer. A
   rule-based extractor reads the filter from the question instead. One detail worth keeping:
   "late" maps to comparing arrival against estimate, not to `status = 'delayed'`, because a
   shipment can be marked delivered and still have arrived late.

Two smaller ones in the mock, both visible only in a real answer: it repeated the same clause
three times when that clause appeared in three chunks, and it quoted the source header
`(contract.pdf, page 4, 4.2 Late Delivery)` back as if it were content.

Worth stating plainly: 294 tests were green while the system could not answer a single
question. Every one of those three came from running it, not from the suite.

296 backend tests, 91 percent coverage. Image sizes: api 2.21 GB and worker 2.37 GB, both
carrying torch and the model, against 419 MB for an api with neither.

Next: phase 7, the dashboard.

## 2026-09-23 - Phase 7, the dashboard

Seven pages: sign in, sign up, dashboard, shipments, suppliers, documents, ask, alerts and
settings.

Shape of it:
- Types are generated from the running api's openapi schema, so a backend change the frontend
  has not caught up with is a type error rather than a runtime surprise.
- The access token lives in a module variable, not in storage. An xss can read localStorage and
  cannot read a closure. The refresh cookie survives a reload, and the app exchanges it for a
  token at startup behind a splash, so the login page does not flash on every reload.
- One refresh at a time. Five requests expiring together would otherwise fire five refreshes,
  rotation would revoke four of each other, and the user would be signed out for no reason they
  could see. There is a test with five parallel requests that asserts exactly one refresh.
- Filters live in the url. A reload keeps them, the back button works, and a filtered view is
  shareable by copying the address bar. Changing a filter resets to page one, because staying on
  page three of a different result set shows an empty table.
- Server-side paging and sorting only. Fetching everything to sort it in the browser stops
  working at the first customer with real data.
- Every chart sits in a fixed-height box, because ResponsiveContainer measures its parent and a
  parent with no resolved height measures zero and renders nothing at all.
- The document list polls while anything is in flight and stops as soon as everything reaches a
  terminal state. A fixed interval would keep asking forever and for nothing.
- Answers render as text. Rendering model output as html would let an uploaded document decide
  what runs in the browser.
- Signing out clears the query cache, otherwise the next account to sign in on the same browser
  sees the previous one's lists before the refetch lands.

`exactOptionalPropertyTypes` is off, and the reason is in the tsconfig: react props are
routinely passed as `prop={maybeUndefined}` and third-party prop types such as react-router's
`NavLinkProps` are not written to accept it, so the flag produced casts rather than caught
bugs. `strict` and `noUncheckedIndexedAccess` stay on and did catch real ones.

Review findings:
1. **The browser was calling the api cross-origin.** `VITE_API_BASE_URL` pointed at
   `localhost:8000`, which bypassed both the vite dev proxy and the nginx proxy built for this,
   added a preflight to every request, and would have baked a hostname into a production
   bundle. An empty base url means relative paths on one origin, proxied in both environments.
2. **The side panels could not be closed from a keyboard.** The backdrop click and the close
   button are both mouse-only. Extracted a `SidePanel` that closes on Escape, moves focus
   inside on open, and announces itself as a dialog.
3. **`·` rendered as five literal characters.** It is an escape inside a template literal
   and plain text inside a jsx node, and the supplier panel was showing
   "6 shipments · 1 late" on screen. Only visible by looking at the page.

30 frontend tests. Initial bundle 92 kB gzipped, with the charts split into the dashboard's own
chunk at 117 kB so nothing else pays for them.

Next: phase 8 is the optional risk classifier, or straight to observability.

## 2026-09-24 - Phase 9, observability and testing

Phase 8 (the risk classifier) is skipped. A model trained on generated data produces a number
nobody can defend, and the first question about it would be where the labels came from.

Done:
- `app/core/context.py` holds `request_id`, `tenant_id` and `user_id` as `ContextVar`s, and a
  structlog processor copies them onto every record. `ContextVar` not thread local, because one
  thread serves many requests interleaved and a thread local would credit a line to whichever
  request happened to be running.
- Three raw ASGI middlewares rather than `BaseHTTPMiddleware`: request context, access log,
  metrics. `BaseHTTPMiddleware` wraps each request in a task group and a memory stream, which
  costs latency and, because it runs the app in a child task, would lose the tenant that is
  bound deeper in the stack.
- `X-Request-ID` is read from the request when present and generated otherwise, validated
  against `^[A-Za-z0-9._-]{1,64}$`, and returned on the response. It rides the job payload into
  the worker, so one upload greps out as one story:
  `ingest.started`, `ingest.completed` and `embed.completed` all carry `request_id=trace-upload-10`.
- `app/core/metrics.py`: 11 metrics with bounded labels, custom buckets per workload, and a
  tenant cap of 50 with the rest folded into `other`.
- Health split into `/health/live` (touches nothing), `/health/ready` (three dependencies, 2s
  each, concurrent) and `/health/info`. `/health` stays as an alias of readiness. The container
  healthcheck now points at liveness.
- Prometheus and Grafana in `docker-compose.observability.yml` behind a profile, with an
  8 panel dashboard provisioned from the repo. `make up-obs`, `make down-obs`.
- `scripts/check_critical_coverage.py` enforces 90 percent on the six modules that decide who
  sees whose data, separately from the project-wide 70.
- `docs/observability.md` and `docs/testing.md`.

Bugs found by running it:
1. **The route label was missing the API prefix.** FastAPI 0.141 keeps included routers nested
   instead of flattening them, so `scope["route"].path` is the path the inner router declared:
   `/shipments/{shipment_id}`, not `/api/v1/shipments/{shipment_id}`. Every dashboard query
   written against the real URL would have matched nothing. The route's segments are the tail
   of the request's, so the label is now built by aligning the two from the right, which also
   survives a FastAPI that flattens routers again.
2. **Every Grafana panel would have been empty.** The dashboard JSON refers to datasource uid
   `prometheus`; a provisioned datasource without an explicit `uid` gets a generated one
   (`PBFA97CFB590B2093` here). Pinned the uid in the provisioning file. Visible only by opening
   Grafana, not by any check of the files.
3. **The critical-coverage gate failed on its first run**, at 85 percent for the pgvector store.
   The gap was real: `delete_document` had no test and no caller, and `as_items` had no caller
   at all. Removed the dead helper and added three tests, including one that shows deleting
   another tenant's document removes nothing.
4. **`npm run gen:api` could not run.** It called `openapi-typescript`, which is not a
   dependency and cannot be one: version 7 peer-depends on TypeScript 5 and this project is on
   6. The script now runs it through `npx` and pipes the result through prettier, which is what
   keeps the generated file from rewriting itself on every run.

Review findings:
1. **The request id pattern accepted a trailing newline.** In Python `$` also matches just
   before one, so `abc\n` passed a check written to stop exactly that. The HTTP parser rejects
   such a header first, which is the reason the second line of defence has to be right on its
   own. `\A...\Z` now.
2. **The route label picked the wrong segment when an id repeated a literal.** The first
   attempt substituted parameter values into the path, so a shipment whose id was the string
   `shipments` produced `/api/v1/{shipment_id}/shipments`. Replaced with aligning the route's
   segments against the tail of the request's, which needs no value matching and gives the same
   answer whether or not FastAPI flattens its routers.
3. **Probes and scrapes were the log.** Kubernetes probes every few seconds and Prometheus
   every fifteen, at an access line each. `/metrics` and the health paths are now logged only
   when they answer with an error.
4. **A failing embedding job was invisible.** Only the success path recorded a metric, so a job
   that kept failing showed up as a gap where a completion should be rather than as a count.

Measured on the running stack: `/metrics` scrape 4.7 ms, access log adds about 0.1 ms per
request, 315 backend tests in 64 s, coverage 92.5 percent.

Next: phase 10, Kubernetes manifests, Terraform and CI.

## 2026-09-24 - Phase 10, containers, Kubernetes and infrastructure as code

Done:
- `infra/k8s/base`, a Kustomize base of 14 manifests, with a local overlay that adds Postgres,
  Redis and MinIO, and a staging overlay that replaces them with ExternalName services pointing
  at RDS and ElastiCache and swaps the Secret for an `ExternalSecret`.
- Three probes on the api, each answering a different question. `startupProbe` gives the model
  two minutes to load and suspends the other two while it runs, which is what stops a slow start
  from being killed in a loop. `livenessProbe` hits `/health/live`, which touches nothing.
  `readinessProbe` hits `/health/ready`, so a pod with a broken dependency leaves the Service
  rather than the cluster.
- Migrations as a Job, not an init container: an init container runs once per pod, so two api
  replicas would race each other through alembic.
- `maxUnavailable: 0` plus `preStop: sleep 5`. Kubernetes sends SIGTERM and removes the endpoint
  at the same time and the two are not atomic, so without the sleep a rolling update drops the
  requests still in flight.
- Worker `terminationGracePeriodSeconds: 320` against an arq `job_timeout` of 300, and memory
  requests equal to limits so the pod is Guaranteed and a node under pressure evicts something
  else rather than losing a job.
- HPA on CPU for the api with a 30s window out and 300s in. The worker gets a KEDA
  `ScaledObject` on queue depth instead, because it waits on I/O and its CPU stays flat while the
  queue grows. KEDA is not installed in the demo cluster, so that file is outside every overlay
  and CI validates it against the published CRD schema.
- NetworkPolicy default deny plus four explicit allows. Applied but not enforced on kind, whose
  default CNI ignores them.
- Every pod non-root, read only root filesystem, no privilege escalation, all capabilities
  dropped. The web image moved to the unprivileged nginx build, which listens on 8080 as uid 101.
- `scripts/smoke_test.sh`: login, upload, wait for indexed, ask, require citations. One
  definition of working, used by compose, by kind and by CI.
- Terraform: network, eks, rds, elasticache, s3 and irsa modules plus a staging environment.
  `terraform validate` passes. Never applied, and `docs/deployment.md` says so with the monthly
  cost that decision is based on.
- Four GitHub Actions workflows. The two that matter most: `api-contract` regenerates the
  frontend types from the OpenAPI schema and fails if they differ from what was committed, and
  the security workflow runs `check_ai_traces.sh` over the full history so that requirement stops
  depending on anyone remembering.

Bugs found by running it:
1. **A deadlock in the readiness probe added last phase.** `/health/ready` checks the object
   store with `head_bucket`, but nothing created the bucket except the upload path, and a pod
   that is not ready never receives an upload. The compose stack already had the bucket, so it
   only appeared on a cluster built from nothing. The bucket is ensured at startup now.
2. **`kubectl apply -k` created the migration Job before Postgres existed**, and it burned its
   retries on DNS. Fixed with an init container that waits for the port rather than by telling
   the caller to apply twice in the right order.
3. **The MinIO tag in the overlay did not exist.** The compose stack pulls
   `quay.io/minio/minio:RELEASE.2024-11-07T00-52-20Z`; a second tag was a second thing to keep
   current, so both now use the same one.
4. **`kubectl wait` fails when the resource does not exist yet**, which is exactly the state
   right after `kubectl apply` submits it. `kind-up.sh` polls for the deployment to appear and
   then waits on the rollout.
5. **A kind cluster can outlive its kubeconfig entry**, for example across a docker daemon
   restart. `kind-up.sh` re-exports it rather than reporting that no context exists.

Review findings:
1. **The worker probe could never pass.** It ran `pgrep -f arq`, and `pgrep` is not in the
   image. Replaced with `arq worker.settings.WorkerSettings --check`, which reads the heartbeat
   the worker writes into Redis and so tells a wedged event loop from a healthy one, which the
   process check could not have done even if it had run.
2. **The KEDA trigger read an environment variable that does not exist.** `REDIS_HOST_PORT` was
   never set anywhere. The scaler wants host and port, not a dsn, so `REDIS_ADDRESS` is now its
   own entry in the ConfigMap rather than a second parse of `REDIS_URL`.
3. **The local overlay's replica patch did nothing.** It set the api to one replica while the
   HPA's `minReplicas: 2` immediately put the second one back. The overlay patches the HPA too.
4. **A second `kind-deploy` would have failed.** A Job's pod template is immutable, so applying
   over a completed Job is an error rather than a no-op. The script deletes it first.
5. **The resource numbers were guesses.** `kubectl top` reports the api at 445 MiB idle and the
   worker at 441 MiB, and `docker stats` puts them at 766 MiB and 661 MiB under load. The
   worker's 2Gi request was nearly triple what it needs. Now 800Mi and 1Gi, with the reasoning
   in the manifest.

Verified on the cluster rather than asserted: `kubectl rollout restart deploy/api` with a
request every second through the ingress returned forty consecutive 200s, and
`scripts/smoke_test.sh` passes against `http://localhost:8081`, upload through indexing to an
answer with two citations.

Environment note: the machine ran out of disk in the middle of this, and Docker's own metadata
store started returning I/O errors, which is what `kind load` failed on. 28 GB of build cache
and 5 GB of application caches later it recovered. Worth knowing before blaming the manifests.

Next: phase 11, architecture documentation and the demo package.

## 2026-09-24 - Phase 11, documentation and the first green pipeline

Done:
- Eleven decision records in `docs/adr`, Nygard format with one addition: every record ends
  with a `Revisit when` condition. A decision that cannot say what would make it wrong is a
  preference with a heading.
- `docs/architecture.md` with five Mermaid diagrams: the container view, the five isolation
  layers, ingestion, answering a question, and the token lifecycle. Mermaid because it renders
  on GitHub, diffs in review, and is edited in the same commit as the code it describes.
- `docs/security.md`, fourteen threats each with a residual risk column. The column is the
  point: the log redaction is a denylist on key names and does not look at values, and prompt
  injection is reduced to a wrong answer rather than removed.
- `docs/performance.md` with `scripts/bench.py` output and two query plans. The plan for the
  shipment list shows the RLS policy as a `One-Time Filter`, evaluated once per statement and
  not per row, which answers the usual objection to row-level security.
- `docs/demo.md`, a five minute walkthrough plus a table mapping likely questions to the file
  that answers them.
- `scripts/audit_repo.sh`, `CONTRIBUTING.md`, and a rewritten README that leads with an answer
  and a citation, then measured results and ten known limitations.

Things the documentation had to be honest about rather than dress up:
- The cache saves nothing measurable at 320 rows. The miss and hit numbers are in the document
  instead of a claimed speedup.
- The full text query plan is a sequential scan, because 81 rows fit in three pages and the
  planner is right to ignore the GIN index. The index is justified by the size the table
  reaches, which is the argument rather than the current plan.
- `statistics.quantiles` with its default method extrapolates, and the first benchmark run
  reported a p99 above the observed maximum.

The first CI run was red five times, all of them real:
1. **The MinIO image is no longer pullable at all.** Docker Hub and quay both answer 401 to an
   anonymous pull, so `make up` fails on any machine that has not cached it, which is every
   machine except this one. For a repository whose first promise is that it runs, that is the
   worst kind of bug, and only CI on a clean runner could have found it. Swapped for the same
   server published by Bitnami, which also starts without arguments and so fits a services
   entry. A named volume is created owned by root and the image runs as uid 1001, so compose
   takes the directory as root and Kubernetes uses `fsGroup`.
2. **mypy was green locally and red in CI.** `uv sync` without `--all-groups` leaves the
   optional providers uninstalled, so mypy treated the anthropic import as Any and checked
   nothing. With them installed it found two real problems: a bare dict literal matches none of
   the `create` overloads, and this version of the sdk no longer types `temperature`. `make
   install` now installs every group so local and CI agree.
3. **pip-audit could not resolve the export**, because torch pins to a `+cpu` build that lives
   only on the pytorch index. The ai and ml groups are excluded with the reason written down.
4. **trivy-action 0.29.0 does not exist**, and the tags carry a `v`.
5. **checkov found twenty findings.** Twelve fixed: envelope encryption for Kubernetes secrets,
   all five control plane log types, VPC flow logs with a year of retention, IAM database
   authentication, forced TLS to Postgres, enhanced monitoring, encrypted performance insights,
   a customer managed key for ElastiCache, a written key policy, pinned availability zones and
   tags copied to snapshots. Eight skipped, each with a sentence saying why.

Then pip-audit found a real one: PYSEC-2026-1325 against ecdsa, with no fixed release. ecdsa
is there because python-jose depends on it, and python-jose has not shipped in years. Only
HS256 is used, which PyJWT implements identically, so the library was replaced rather than the
advisory ignored. rsa left the tree with it.

All three workflows green. Rebuilding the compose stack against an empty object store also
proved the startup bucket fix from phase 10: readiness went from `s3: false` to `ok` on its
own, and the smoke test passed from upload through indexing to a cited answer.
