# ADR 004: ARQ for background jobs, not Celery

Date: 2026-09-22
Status: Accepted

## Context

Document ingestion takes tens of seconds: download, parse, chunk, embed, write.
It cannot happen inside the upload request. The rest of the backend is async.

## Decision

ARQ, with Redis as the broker.

## Alternatives considered

| Option | Why not |
|---|---|
| Celery | Synchronous at heart. Async tasks need a bridge, and the parts that matter here (a job that awaits S3 and Postgres) fight the execution model. Also brings a configuration surface far larger than this needs |
| RQ | Synchronous too, and no async support at all |
| FastAPI BackgroundTasks | Runs in the API process: an upload that takes 40 seconds of CPU competes with request handling, and a restart loses the work |
| SQS plus a custom consumer | Another managed dependency and a consumer to write, for a queue Redis already provides |

## Consequences

Positive: jobs are plain async functions using the same session helpers,
retries and timeouts are configuration, and Redis is already present for caching
and rate limiting.

Negative: ARQ is a small project with a small ecosystem. There is no result
backend beyond Redis, no built-in scheduling beyond cron jobs, and no flower
equivalent. Queue depth has to be read from Redis directly, which is what the
KEDA trigger does.

Revisit when: jobs need routing across several queues with different priorities
and per-queue concurrency, or the operational tooling around Celery becomes
worth its weight.
