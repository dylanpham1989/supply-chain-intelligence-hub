"""Prometheus metrics.

Every label here is bounded on purpose. Prometheus keeps one time series per
distinct combination of label values, so a label that can take unbounded values
(a URL with an id in it, a tenant id on a platform with 10k tenants) multiplies
the series count until the server runs out of memory. The two places that could
go unbounded are handled explicitly: routes are labelled with their template,
and tenants are capped at MAX_TENANT_LABELS with the rest folded into "other".

Per-tenant detail beyond the cap belongs in logs, where cardinality is cheap.
"""

from typing import Any
from uuid import UUID

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# The default buckets stop at 10s, which is fine for HTTP and useless for an LLM
# call that takes 2-6s: everything lands in one bucket and p95 becomes a guess.
HTTP_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
LLM_BUCKETS = (0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0, 20.0, 30.0)
INGEST_BUCKETS = (0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0)
HIT_BUCKETS = (0.0, 1.0, 2.0, 3.0, 5.0, 8.0, 13.0)

MAX_TENANT_LABELS = 50
OTHER_TENANT = "other"

_tracked_tenants: set[str] = set()

http_requests_total = Counter(
    "http_requests_total",
    "HTTP requests by route template",
    ["route", "method", "status", "tenant"],
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["route", "method"],
    buckets=HTTP_BUCKETS,
)

documents_processed_total = Counter(
    "documents_processed_total",
    "Documents that finished ingestion",
    ["tenant", "doc_type", "status"],
)
document_processing_duration_seconds = Histogram(
    "document_processing_duration_seconds",
    "Time from job pickup to indexed",
    ["doc_type"],
    buckets=INGEST_BUCKETS,
)

rag_queries_total = Counter(
    "rag_queries_total",
    "Questions answered",
    ["tenant", "route_type", "provider"],
)
rag_query_duration_seconds = Histogram(
    "rag_query_duration_seconds",
    "Question latency by stage",
    ["stage"],
    buckets=LLM_BUCKETS,
)
rag_retrieval_hits = Histogram(
    "rag_retrieval_hits",
    "Chunks retrieved per question",
    buckets=HIT_BUCKETS,
)
llm_tokens_total = Counter(
    "llm_tokens_total",
    "Tokens billed by the provider",
    ["provider", "direction"],
)

cache_operations_total = Counter(
    "cache_operations_total",
    "Cache reads by outcome",
    ["result"],
)

worker_jobs_total = Counter(
    "worker_jobs_total",
    "Worker jobs by outcome",
    ["task", "status"],
)

db_pool_connections = Gauge(
    "db_pool_connections",
    "Connections in the SQLAlchemy pool",
    ["state"],
)


def tenant_label(tenant_id: UUID | str) -> str:
    """Bound the tenant dimension.

    The first MAX_TENANT_LABELS tenants seen keep their own series; everything
    after shares one. A demo with ten tenants gets full detail, and a deployment
    with ten thousand does not take Prometheus down.
    """
    value = str(tenant_id)
    if value in _tracked_tenants:
        return value
    if len(_tracked_tenants) < MAX_TENANT_LABELS:
        _tracked_tenants.add(value)
        return value
    return OTHER_TENANT


def record_http(*, route: str, method: str, status: int, tenant: str, duration_s: float) -> None:
    http_requests_total.labels(
        route=route, method=method, status=str(status), tenant=tenant or "anonymous"
    ).inc()
    http_request_duration_seconds.labels(route=route, method=method).observe(duration_s)


def record_document(
    *, tenant_id: UUID | str, doc_type: str, status: str, duration_s: float
) -> None:
    documents_processed_total.labels(
        tenant=tenant_label(tenant_id), doc_type=doc_type, status=status
    ).inc()
    document_processing_duration_seconds.labels(doc_type=doc_type).observe(duration_s)


def record_rag(
    *,
    tenant_id: UUID | str,
    route_type: str,
    provider: str,
    hits: int,
    retrieve_ms: int,
    llm_ms: int,
    total_ms: int,
    token_in: int,
    token_out: int,
) -> None:
    tenant = tenant_label(tenant_id)
    rag_queries_total.labels(tenant=tenant, route_type=route_type, provider=provider).inc()
    rag_query_duration_seconds.labels(stage="retrieve").observe(retrieve_ms / 1000)
    rag_query_duration_seconds.labels(stage="llm").observe(llm_ms / 1000)
    rag_query_duration_seconds.labels(stage="total").observe(total_ms / 1000)
    rag_retrieval_hits.observe(hits)
    # Tokens are the one metric that maps straight to money.
    if token_in:
        llm_tokens_total.labels(provider=provider, direction="in").inc(token_in)
    if token_out:
        llm_tokens_total.labels(provider=provider, direction="out").inc(token_out)


def record_cache(result: str) -> None:
    cache_operations_total.labels(result=result).inc()


def record_job(task: str, status: str) -> None:
    worker_jobs_total.labels(task=task, status=status).inc()


def observe_pool(engine: Any) -> None:
    """Read the pool at scrape time rather than polling it on a timer."""
    pool = getattr(engine, "pool", None)
    checked_out = getattr(pool, "checkedout", None)
    checked_in = getattr(pool, "checkedin", None)
    if callable(checked_out):
        db_pool_connections.labels(state="in_use").set(checked_out())
    if callable(checked_in):
        db_pool_connections.labels(state="idle").set(checked_in())


def render() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
