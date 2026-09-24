# Performance

Every number here was measured on the machine described below and the command
that produced it is next to it. None of it is a projection.

**Machine**: Apple Silicon laptop, Docker Desktop, Postgres 16 and Redis 7 in
containers, api and worker in containers, everything on one host.

**Data**: the seeded demo set. 320 shipments across two tenants, 81 document
chunks. That size matters, and where it changes the answer it is said so.

## Endpoint latency

```bash
cd backend && uv run python -m scripts.bench --runs 60
```

```
60 requests each, sequential, against http://localhost:8000

endpoint                   p50       p95       p99       max  cache
shipments, page 1         3.1ms      3.8ms      5.4ms      7.5ms
shipments, filtered       2.9ms      4.2ms      7.0ms      8.5ms
shipments, page 5         2.7ms      3.1ms      3.2ms      3.3ms
analytics summary         1.9ms      2.4ms      2.9ms      3.4ms  hit
analytics timeseries      2.1ms      2.6ms      3.1ms      3.4ms  hit
suppliers                 2.5ms      3.4ms      5.4ms      8.0ms
documents                 3.0ms      6.1ms      7.2ms      7.4ms
health, ready             2.6ms      4.2ms      4.6ms      4.7ms
```

Sequential, one client. This measures what a request costs, not what the system
can absorb. There is no load test here, and the numbers should not be read as
capacity.

## What the cache is worth at this size

```bash
docker compose exec redis redis-cli FLUSHDB
curl -w "%{time_total}" .../analytics/summary   # miss
curl -w "%{time_total}" .../analytics/summary   # hit
```

```
miss 5.1ms  hit 2.9ms
miss 3.6ms  hit 3.1ms
miss 3.4ms  hit 3.3ms
```

Almost nothing. Aggregating 320 rows costs less than the Redis round trip saves,
so at this size the cache is overhead with a good story attached.

It is still the right shape: the summary endpoint aggregates the whole shipment
table per tenant, and that cost grows with the tenant while the cached response
does not. The honest statement is that the cache is built for a data size this
demo does not have, and the hit and miss numbers above are the evidence for
saying so rather than claiming a speedup that is not there.

## Row-level security, in the query plan

The interesting part of this plan is the `One-Time Filter`.

```sql
BEGIN;
SELECT set_config('app.tenant_id', '<uuid>', true);
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT * FROM shipments
WHERE tenant_id = '<uuid>'
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

```
 Limit (actual time=0.142..0.144 rows=20 loops=1)
   Buffers: shared hit=15
   ->  Incremental Sort (actual time=0.142..0.142 rows=20 loops=1)
         Sort Key: created_at DESC, id DESC
         Presorted Key: created_at
         ->  Result (actual time=0.041..0.054 rows=39 loops=1)
               One-Time Filter: ((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid = '<uuid>'::uuid)
               ->  Index Scan Backward using ix_shipments_tenant_created on shipments
                     Index Cond: (tenant_id = '<uuid>'::uuid)
 Planning Time: 0.420 ms
 Execution Time: 0.210 ms
```

Two things worth reading off it:

The policy is evaluated **once**, not per row. `current_setting` is stable
within the statement, so the planner hoists the comparison out as a one-time
filter. The common objection to row-level security, that it costs a predicate
evaluation on every row, does not apply to a policy written this way.

The `(tenant_id, created_at)` index does the ordering as well as the filter, so
the sort is incremental rather than a full sort of the tenant's rows. That index
exists because the tenant mixin's default `index=True` was removed: it had
created eight single-column indexes that no query used, and the composite ones
the queries actually need were added explicitly.

## Full text search, and what the plan says at this size

```sql
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT id, ts_rank_cd(content_tsv, websearch_to_tsquery('english', 'late delivery penalty'))
FROM document_chunks
WHERE tenant_id = '<uuid>'
  AND content_tsv @@ websearch_to_tsquery('english', 'late delivery penalty')
ORDER BY 2 DESC LIMIT 10;
```

```
 ->  Seq Scan on document_chunks (actual time=1.064..1.978 rows=7 loops=1)
       Filter: ((tenant_id = '<uuid>') AND (content_tsv @@ '''late'' & ''deliveri'' & ''penalti'''))
       Rows Removed by Filter: 74
 Execution Time: 2.234 ms
```

There is a GIN index on `content_tsv` and the planner ignored it, correctly: 81
rows fit in three pages, and an index lookup plus a heap fetch costs more than
reading them. The index is there for the size this table reaches after a few
hundred documents, not for the demo.

Saying "we have a GIN index" while the plan shows a sequential scan would be a
claim the evidence contradicts. The index is justified by what the table becomes,
and that is the argument, not the current plan.

## Ingestion and embedding

From the worker log for a 6 page contract:

```
ingest.completed   chunks=11  duration_ms=320
embed.completed    embedded=11 duration_ms=211  model=all-MiniLM-L6-v2
```

Parsing and chunking dominate for a text PDF. Embedding 11 chunks on CPU in
batches of 32 is one batch, which is why it is fast; a 200 page document is
seven batches and scales close to linearly.

## Observability overhead

`/metrics` renders in 4.7ms with the default collectors plus eleven application
metrics. The access log and metrics middlewares together add about 0.1ms per
request, measured as the difference between the middleware timer and the
endpoint's own time.

## Test suite

```bash
make test
```

315 backend tests in 64 seconds against real Postgres, Redis and MinIO, plus 30
frontend tests in about 1 second. Coverage 92.5 percent overall, with a separate
90 percent floor on the six modules that decide who sees whose data.

## Images

| Image | Size | What is in it |
|---|---|---|
| api | 2.21 GB | torch CPU wheels and the embedding model, needed to embed the question on the read path |
| worker | 2.38 GB | the same, plus the PDF and CSV parsers |
| web | 77 MB | nginx unprivileged plus the built bundle |

The api was 419 MB before it needed to embed questions locally. Carrying torch
for that is the single largest cost in this project's images, and a hosted
embedding endpoint would remove about 1.7 GB from both at the price of a network
call per question and a per-token bill.

Frontend bundle: 92 kB gzipped for the initial load, with the charts split into
the dashboard's own 117 kB chunk so nothing else pays for Recharts.

## What is not measured

No load test, no concurrency numbers, no p99 under saturation. No measurements
against a realistic dataset: 320 shipments is three orders of magnitude below
where the pagination and index decisions start to matter, which is exactly why
[ADR 005](adr/005-offset-pagination.md) states the ceiling rather than claiming
there is not one.
