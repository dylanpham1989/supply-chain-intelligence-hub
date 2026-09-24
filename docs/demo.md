# Demo script

Five minutes, in the order that answers the most likely questions before they
are asked. Multi-tenancy comes second rather than last, because it is the
strongest claim in the project and the one worth spending attention on.

## Before the call

```bash
make up && make migrate && make seed
```

Open two browser windows, signed in as different tenants:

- `acme-logistics` / `admin@acme.test` / `Demo1234!`
- `globex-industrial` / `analyst@globex.test` / `Demo1234!`

Have a terminal ready with the repository open.

## 0:00 What it is

The Acme dashboard. Point at the on-time rate, the delayed shipments by month,
and the supplier table.

"Two tenants, a few hundred shipments each, seeded deterministically. Everything
on this page is one cached query."

## 0:45 Multi-tenancy

Switch to the Globex window. Different numbers, different suppliers, same code.

Then show it is not a UI filter. Take a shipment id from Acme and ask for it
with the Globex token:

```bash
curl -s -H "Authorization: Bearer $GLOBEX_TOKEN" \
  localhost:8000/api/v1/shipments/$ACME_SHIPMENT_ID
```

404, not 403: Globex cannot distinguish "not yours" from "does not exist", which
is the correct answer to give.

"The filter is a Postgres row-level security policy, not an `if` in the service
layer. The tenant comes from a signed claim and is set per transaction. There
are tests that delete the application's own filter and check the database still
refuses."

## 1:45 Ingestion

Upload `data/samples/contract_acme_supply_2026.pdf`. The status moves from
pending to processing to indexed, and the list stops polling when it gets there.

```bash
docker compose logs worker --no-log-prefix | grep <request-id>
```

"The request id from the upload response header appears in the worker's logs.
One upload, one id, from the API call to the last vector."

## 2:45 Retrieval

Ask: **What is the penalty for late delivery?**

The answer arrives with citation chips. Click one, and it opens the clause it
came from.

"It cites because a model that cannot cite is a model that is guessing.
Retrieval is vector search and Postgres full text search fused with reciprocal
rank fusion, not one or the other."

Then ask: **Show late deliveries to the EU in Q1**

"That one does not go through retrieval at all. An intent router sends it down a
SQL path, and the model's only job is to produce a JSON filter that Pydantic
validates. The model never writes SQL. The worst case of a bad filter is a
validation error and a fallback to retrieval."

## 3:45 Operations

```bash
curl -s localhost:8000/metrics | grep rag_query_duration_seconds_bucket | head -3
curl -s localhost:8000/health/live    # 200, touches nothing
docker compose stop redis
curl -s localhost:8000/health/ready   # 503, names redis
```

The dashboard still loads with Redis down: the cache fails open.

"Liveness touches nothing on purpose. A liveness probe that checks the database
turns a slow database into a restart of every pod at once."

If the kind cluster is already up:

```bash
kubectl get pods -n scih
kubectl get hpa -n scih
```

## 4:30 What is missing

Open `README.md` at Known limitations.

"That is what I did not build and why. The Terraform is validated and scanned
but never applied, and there is a cost table explaining that choice."

## Questions and where the answer lives

| Question | Where |
|---|---|
| How is tenant isolation enforced? | [ADR 002](adr/002-shared-schema-rls.md), `backend/app/db/rls.py`, `backend/tests/integration/test_rls.py` |
| Why not a schema per tenant? | [ADR 002](adr/002-shared-schema-rls.md), Alternatives |
| Where do you keep the access token, and why? | [ADR 003](adr/003-jwt-refresh-rotation.md), `frontend/src/lib/api-client.ts` |
| What happens if a refresh token is stolen? | [ADR 003](adr/003-jwt-refresh-rotation.md), `test_refresh_token_reuse_revokes_family` |
| Why ARQ and not Celery? | [ADR 004](adr/004-arq-over-celery.md) |
| What breaks first at scale? | [ADR 005](adr/005-offset-pagination.md), Known limitations |
| Why pgvector instead of a vector database? | [ADR 006](adr/006-pgvector-default.md) |
| How do you stop the model writing SQL? | [ADR 007](adr/007-llm-emits-filters-not-sql.md), `backend/ai/rag/structured.py` |
| How do you scale the worker? | [docs/deployment.md](deployment.md), `infra/k8s/base/worker-keda.yaml` |
| Why is there no risk model? | [ADR 009](adr/009-no-risk-classifier.md) |
| Why is nothing deployed to AWS? | [ADR 010](adr/010-kubernetes-local-vs-cloud.md), cost table in [docs/deployment.md](deployment.md) |
| How do you debug a failed ingestion? | [docs/observability.md](observability.md), correlation id section |
| What is your test strategy? | [docs/testing.md](testing.md) |
| What are you worried about security-wise? | [docs/security.md](security.md), residual risk column |
