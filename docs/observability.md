# Observability

Two of the three pillars are here: logs and metrics. Tracing is deliberately left out, and
the reasoning is at the end.

## Logs

Every line is a JSON object on stdout, which is where a container's logs belong. Locally the
console renderer prints the same records in colour, because reading JSON by eye is a waste of
attention.

Events are named `domain.action.state`: `auth.login.failed`, `ingest.completed`,
`rag.answered`, `http.request`. The name is the stable part, so a dashboard or an alert keyed
on it survives a reworded message.

Fields, not interpolation:

```python
log.info("ingest.completed", document_id=str(doc_id), chunks=42, duration_ms=1180)
```

A query for `event="ingest.completed" AND tenant_id="..."` is a filter. The same information
inside a formatted sentence is a regex, and at ten million lines a regex is not an option.

### Correlation

`app/core/context.py` holds three `ContextVar`s: `request_id`, `tenant_id`, `user_id`. A
structlog processor copies them onto every record, so nothing has to be threaded through call
signatures.

`ContextVar` rather than a thread local, because the server is asynchronous: one thread
interleaves many requests, and a thread local would hand a log line to whichever request
happened to be running.

The id comes from the `X-Request-ID` header when the caller sends one, so a trace survives a
proxy hop, and is generated otherwise. A caller-supplied value is validated against
`^[A-Za-z0-9._-]{1,64}$` first: it ends up in log records, and a newline in it would let a
caller write log lines of their own.

It reaches the worker too. `process_document` takes the request id as a job argument and binds
it, and passes it on when it enqueues `embed_document`. One upload, one id, and every line
from the API call through parsing to the last vector comes back from a single grep:

```bash
docker compose logs --no-log-prefix | grep <request-id>
```

### Redaction

A processor blanks any key matching `api[_-]?key|authorization|password|passwd|token|secret`
before rendering. One log of a request header without it and an API key is in the aggregator
permanently.

The rule is a denylist on key names, which is the weaker of the two designs. Values are not
scanned, so a credential passed under an innocent key still gets through. The stronger design
is an allowlist of fields safe to log; it costs more to maintain and was not worth it here.

Request bodies, chunk text and model answers are never logged. Shipment rows carry customer
data and contract chunks are the customer's document; `chunk_count` and `answer_length` say
what operations needs to know.

## Metrics

`/metrics` renders the Prometheus text format. Prometheus itself lives in
`docker-compose.observability.yml` under a profile, so the default stack does not pay 400 MB
of RAM for it:

```bash
make up-obs     # prometheus :9090, grafana :3001
make down-obs
```

### Cardinality

Prometheus keeps one time series per distinct combination of label values, in memory. The two
labels here that could grow without bound are handled explicitly.

**Routes** are labelled with their template. `/api/v1/shipments/{shipment_id}` is one series;
`/api/v1/shipments/<uuid>` would be one series per shipment, and anyone who can reach the API
could add more by asking for paths that do not exist. Unmatched paths all share the label
`unmatched`.

Getting the template is less obvious than it looks. FastAPI keeps included routers nested
rather than flattening them, so `scope["route"].path` is the path that router declared,
`/shipments/{shipment_id}`, without the `/api/v1` prefix the request actually used. A label
like that matches nothing anyone would type into a dashboard.

Those segments are the tail of the request's, so the two are aligned from the right and the
missing prefix is taken from the request path. Substituting the parameter values by hand is
the obvious alternative and it is wrong: an id whose value equals an earlier literal segment
rewrites that segment instead, and the label becomes a route that does not exist. Aligning
also keeps working if a later FastAPI starts flattening routers again.

**Tenants** are capped. The first 50 tenant ids seen keep their own series and everything
after shares `other`:

```python
MAX_TENANT_LABELS = 50
```

Ten demo tenants get full detail and ten thousand real ones do not take the server down. Where
per-tenant detail is needed beyond the cap, it is in the logs, where cardinality is cheap.

### Buckets

Prometheus defaults stop at 10 seconds. That is a reasonable range for HTTP and useless for a
language model call that takes two to six seconds, where everything lands in one bucket and
p95 becomes whatever the bucket boundary is.

```python
HTTP_BUCKETS   = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5)
LLM_BUCKETS    = (0.5, 1, 2, 3, 5, 8, 12, 20, 30)
INGEST_BUCKETS = (0.1, 0.5, 1, 2, 5, 10, 30, 60, 120)
```

### What is collected

| Metric | Type | Labels |
|---|---|---|
| `http_requests_total` | counter | route, method, status, tenant |
| `http_request_duration_seconds` | histogram | route, method |
| `documents_processed_total` | counter | tenant, doc_type, status |
| `document_processing_duration_seconds` | histogram | doc_type |
| `rag_queries_total` | counter | tenant, route_type, provider |
| `rag_query_duration_seconds` | histogram | stage (retrieve, llm, total) |
| `rag_retrieval_hits` | histogram | |
| `llm_tokens_total` | counter | provider, direction |
| `cache_operations_total` | counter | result (hit, miss, error) |
| `worker_jobs_total` | counter | task, status |
| `db_pool_connections` | gauge | state (in_use, idle) |

`llm_tokens_total` is the one that maps to money. Latency tells you the system is slow; tokens
tell you the bill.

The pool gauge is read when `/metrics` is scraped rather than polled on a timer, so it costs
nothing between scrapes.

### Limits worth knowing

The worker has no metrics endpoint. It is not an HTTP server, and giving it one to be scraped
means either a push gateway or a sidecar; its work is visible through `documents_processed_total`,
which the API scrapes from the same Redis-backed pipeline. Queue depth is not exported for the
same reason.

Multiple uvicorn workers in one container would each keep their own counters and a scrape would
see whichever answered. The deployment runs one process per pod and scales by pod, which is how
Kubernetes expects to scale anyway. Running several would need `PROMETHEUS_MULTIPROC_DIR` and
the multiprocess collector.

`/metrics` is not exposed publicly. The nginx image returns 404 for it, and in Kubernetes
Prometheus reaches the pod directly on the cluster network.

### Log volume

Kubernetes probes every few seconds and Prometheus scrapes every fifteen. At one access line
each that is most of the log volume and none of its value, so `/metrics` and the health paths
are logged only when they answer with an error.

## Health probes

| Endpoint | Checks | Kubernetes uses it for |
|---|---|---|
| `/health/live` | nothing | restart the pod on failure |
| `/health/ready` | Postgres, Redis, S3, 2s each | take the pod out of the load balancer |
| `/health/info` | nothing | version, git sha, build time |

The split is the point. If liveness checked the database, one slow database would fail the
probe on every pod at once, Kubernetes would restart all of them, and the reconnect storm would
keep the database slow. The cluster would never converge, and the outage would be self
inflicted. `/health/live` returns `{"status": "ok"}` and touches nothing, and a test asserts it
by making every dependency probe raise.

Readiness runs its three checks concurrently, each under `asyncio.wait_for(..., 2.0)`, and
answers 503 with a per-dependency breakdown when any fails. `/health` is kept as an alias of
readiness for probes that already point at it.

## Why no tracing

Distributed tracing earns its cost when a request crosses many services and the question is
which hop is slow. Here there are two processes, and the request id already stitches their logs
together. `rag_query_duration_seconds{stage=...}` answers the one latency-breakdown question
that matters, which is retrieval against generation.

OpenTelemetry would be the choice if this grew a third and fourth service: instrument
FastAPI, SQLAlchemy and httpx, export OTLP to Tempo or Jaeger, and keep the same request id as
the trace id.
