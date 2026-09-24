# Contributing

## Setup

```bash
make install     # uv sync for the backend, npm ci for the frontend
make up          # postgres, redis, minio, api, worker, web
make migrate
make seed
```

The tests need those services running, because they run against the same
Postgres the application uses. There is no SQLite mode and there will not be
one: row-level security, pgvector and the full text search column are the things
worth testing, and SQLite has none of them.

## Before pushing

```bash
make verify      # lint, typecheck, tests, assistant-trace audit
```

`make fmt` fixes most lint findings. `make test-cov` also enforces a 90 percent
floor on the modules that decide who sees whose data.

## Branches and commits

`main` is what is deployed. `dev` is where phases land. Work happens on a branch
off `dev` and merges back through a pull request.

Commit messages say why, in the body, when the why is not obvious. The subject
is lowercase, imperative, and names the area it touches:

```
feat(api): correlate logs, export metrics, split the health probes
fix(worker): stop doubling chunks when a job is redelivered
```

Commits carry no assistant attribution. `scripts/check_ai_traces.sh` enforces
that and runs in CI over the full history.

## Changing the API

The frontend types are generated from the OpenAPI schema. After changing a
request or response model:

```bash
npm --prefix frontend run gen:api
```

CI fails if the committed types do not match the schema.

## Migrations

```bash
make revision m="add supplier rating"
make migrate
```

Autogenerate does not notice everything. Check the generated file, especially
for enum changes and for indexes, and make sure `downgrade` is real rather than
`pass`. Migrations must not import application code: the model that the
migration was written against will not be the model that exists in a year.
