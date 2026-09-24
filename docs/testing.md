# Testing

```bash
make up          # the suite needs postgres, redis and minio
make test        # backend and frontend
make test-unit   # only what runs without services
make test-cov    # coverage report plus the per-module floors
```

## Shape

311 backend tests, 164 of them unit and 147 integration, plus 30 frontend tests. The whole
backend suite runs in about 90 seconds.

The ratio is the point. Unit tests are cheap, so there are many; integration tests are slower
but are the only ones that can prove a database policy works; end-to-end tests are the slowest
and flakiest, so they are the few. A suite built the other way around takes twenty minutes,
fails for reasons nobody trusts, and stops being run.

Integration is heavier here than in a typical service, because the guarantees this project
makes are mostly database guarantees. Row-level security, the tenant predicate on every query,
the generated full-text column, and the vector index are all Postgres behaviour. A unit test
of the code around them proves nothing about them.

## Postgres, not SQLite

SQLite would make the suite faster and the results meaningless. It has no row-level security,
no pgvector, no `tsvector`, no `FILTER`, no `generate_series`. Every guarantee that matters
here would be untested, and the parts that did run would be testing a database the application
never uses.

So the tests run against the same Postgres image as the application, started by
`docker compose`. `conftest.py` fails with the connection string and the reason rather than
skipping quietly, so a missing stack is never mistaken for a passing suite.

## Isolation

Each test gets a connection with an open transaction and a session bound to it, and the
transaction is rolled back afterwards. Rollback is much faster than truncating tables and does
not race when tests run in parallel.

Application code calls `session.commit()`, which would normally end the outer transaction and
defeat the rollback, so the session joins it with `join_transaction_mode="create_savepoint"`:
the inner commit releases a savepoint and the outer rollback still undoes everything.

## Coverage

The project gate is 70 percent, currently at 92. The number on its own means little; a suite
can hit 70 percent by testing getters while leaving the tenant filter untouched.

So `scripts/check_critical_coverage.py` reads `coverage.json` and enforces a 90 percent floor
on the modules that decide who sees whose data:

```
app/core/security.py, app/core/deps.py, app/core/permissions.py,
app/core/cache.py, app/db/rls.py, ai/vectorstore/pgvector_store.py
```

It failed on the first run, at 85 percent for the pgvector store, and the gap was real: the
delete path had no test and a helper had no caller at all.

Coverage is configured with `concurrency = ["greenlet", "thread"]`. SQLAlchemy's async layer
runs awaits inside greenlets, and without that setting every line reached through a database
call is reported as uncovered. It moved the measured number from 89 to 94 without a single new
test.

## The tests that carry the claims

Each of these exists because the README claims something a reader should not have to take on
trust:

| Test | Claim |
|---|---|
| `test_rls.py` | A query without a tenant context returns nothing |
| `test_cache_isolation.py` | Cache keys are namespaced per tenant |
| `test_vector_isolation.py` | Retrieval, vector search and keyword search are each scoped |
| `test_request_scoping.py` | One request's tenant context does not leak into the next |
| `test_auth_flow.py` | Reusing a refresh token revokes the whole family |
| `test_rbac.py` | Every role against every action |
| `test_document_upload.py` | A file that claims to be a PDF and is not gets rejected |
| `test_query_params.py` | An unknown sort column is rejected, not interpolated |
| `test_observability.py` | Liveness touches no dependency; metric labels stay bounded |

## Mutation testing

Coverage says a line ran, not that a test would notice it changing. Several guarantees here
were checked by breaking them on purpose and confirming a test went red.

That exercise found that the vector isolation tests were nearly worthless: deleting the tenant
predicate from the query left all ten passing, because row-level security caught it underneath.
The tests proved the database was configured, not that the code filtered. Two tests were added
that scope the session to one tenant and then ask the store for another's data, which is the
only way to see the application layer on its own.

The results are recorded per phase in `PROGRESS.md`.

## What is not here

No browser end-to-end tests. Playwright would add a browser download, a running stack and two
of the flakiest tests in the suite, to cover flows that the integration tests already cover at
the API level and the component tests cover at the UI level. If this were a product rather than
a portfolio, the demo flow and the two-tenant isolation check are the two that would earn their
keep, and they would run on a schedule rather than on every push.

No load testing. The performance claims in `PROGRESS.md` are single measurements from a laptop,
and they are written as such.
