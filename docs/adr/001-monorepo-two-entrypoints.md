# ADR 001: One repository, one Python project, two entrypoints

Date: 2026-09-22
Status: Accepted

## Context

The system is an HTTP API, a background worker and a browser application. The
API and the worker share models, repositories, settings, logging and the
retrieval code; they differ in how they are started and in which optional
dependencies they need.

## Decision

One repository. One Python project under `backend/` with two entrypoints,
`app.main:app` and `worker.settings:WorkerSettings`, built into two images from
two Dockerfiles that install different dependency groups.

## Alternatives considered

| Option | Why not |
|---|---|
| Separate repositories per service | Every model change becomes a version bump, a release and a coordinated deploy, for two services that are always deployed together |
| One repository, separate Python packages | A shared package needs publishing or path dependencies, and neither buys anything at this size |
| One image running both | The worker needs torch and parsing libraries the api does not, and they scale on different signals |

## Consequences

Positive: a schema change and its migration, its repository method, its endpoint
and its worker use land in one commit and one review. There is one lockfile, so
the api and the worker cannot drift to different versions of SQLAlchemy.

Negative: the images share a build context, so a frontend change invalidates
nothing but a backend change rebuilds both. CI runs the whole test suite for a
one-line change in either.

Revisit when: a second team owns the worker, or the worker's release cadence
needs to be independent of the API's.
