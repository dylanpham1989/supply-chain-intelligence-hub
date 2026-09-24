# Architecture

## System

```mermaid
graph TB
    subgraph browser[Browser]
        WEB[React 19 + TypeScript]
    end

    subgraph cluster[Kubernetes namespace scih]
        ING[ingress-nginx]
        API[FastAPI<br/>2 replicas, HPA on CPU]
        WRK[ARQ worker<br/>scales on queue depth]
    end

    subgraph data[State]
        PG[(PostgreSQL 16<br/>pgvector, RLS)]
        RD[(Redis<br/>cache, queue, rate limit)]
        S3[(S3 or MinIO<br/>documents)]
    end

    subgraph models[Models]
        EMB[MiniLM-L6-v2<br/>384 dim, CPU]
        LLM[LLM provider<br/>mock, Claude, OpenAI, HF]
    end

    WEB -->|same origin| ING
    ING --> API
    ING --> WEB
    API -->|SET LOCAL app.tenant_id| PG
    API -->|read through cache| RD
    API -->|enqueue| RD
    API --> S3
    API --> EMB
    API --> LLM
    RD -->|dequeue| WRK
    WRK --> S3
    WRK --> PG
    WRK --> EMB
```

The api and the worker are the same codebase with different entrypoints and
different dependency groups. Both hold the embedding model: the worker embeds
chunks on the write path, and the api embeds the question on the read path.

## Tenant isolation

This is the part worth understanding first, because everything else assumes it.

```mermaid
graph LR
    A[Signed JWT<br/>tid claim] --> B[get_current_user<br/>dependency]
    B --> C["SET LOCAL app.tenant_id<br/>(transaction scoped)"]
    C --> D[RLS policy<br/>ENABLE + FORCE]
    B --> E[Repository<br/>explicit tenant filter]
    B --> F["Cache key<br/>t:{tenant}:prefix:v1:hash"]
    B --> G[Vector search<br/>tenant predicate]
    D --> H[(rows)]
    E --> H
    F --> I[(redis)]
    G --> H
```

Five layers, and only the first one is the source of truth: the tenant comes
from a signature-verified claim, never from a body, a query parameter or a
header. Below that, the database policy is what holds when application code is
wrong, and the application filters are what hold when a query runs outside a
transaction that set the context.

The layers are not redundant in the way they look. The policy does not reach
Redis, so the cache key carries the tenant itself. Mutation testing showed why
both matter: removing the repository's tenant predicate left every isolation
test passing, because RLS caught it underneath. Two tests now scope the session
to one tenant and ask the store for another's rows, which is the only way to see
the application layer on its own.

## Ingestion

```mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant S as S3
    participant Q as Redis
    participant W as Worker
    participant P as Postgres

    C->>A: POST /documents (pdf or csv)
    A->>A: magic byte check, size cap,<br/>server-generated key
    A->>S: put object
    A->>P: insert document (pending)
    A->>Q: enqueue process_document<br/>with request_id
    A-->>C: 202 Accepted + document_id

    W->>Q: dequeue
    W->>P: status = processing
    W->>S: download
    alt parse fails permanently
        W->>P: status = failed, error recorded
    else parsed
        W->>P: delete then insert chunks (idempotent)
        opt manifest
            W->>P: import shipment rows
        end
        W->>P: status = indexed
        W->>Q: enqueue embed_document
        W->>Q: invalidate cache tags
    end

    W->>P: select chunks where embedding is null
    W->>W: encode in batches of 32
    W->>P: write vectors
```

The delete-then-insert is what makes a redelivered job replace its output rather
than double it. Embedding selects on `embedding IS NULL`, so a repeat run
embeds whatever is still missing and nothing else.

## Answering a question

```mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant R as Router
    participant V as pgvector
    participant K as Postgres FTS
    participant L as LLM

    C->>A: POST /ask
    A->>A: rate limit per tenant
    A->>R: route(question)

    alt structured question
        R->>L: produce a JSON filter
        L-->>R: {status, region, quarter, late_only}
        R->>R: validate with Pydantic (extra=forbid)
        R->>K: SELECT with those filters
        K-->>C: rows plus a described result
    else document question
        R->>V: vector search top k
        R->>K: keyword search top k
        R->>R: reciprocal rank fusion (k=60)
        R->>L: prompt with numbered context
        L-->>R: answer with [1] [2] markers
        R->>R: parse markers into citations
        R-->>C: answer plus citations
    end

    A->>A: record insight row, metrics, tokens
```

A model that cannot cite is a model that is guessing, so the answer carries the
chunks it came from and the UI links each one back to its page in the document.

## Authentication

```mermaid
sequenceDiagram
    participant B as Browser
    participant A as API
    participant P as Postgres

    B->>A: POST /auth/login
    A->>A: constant-time compare, bcrypt in a thread
    A->>P: store sha256(refresh token)
    A-->>B: access token (15 min, memory)<br/>+ refresh cookie (7 d, httpOnly, /api/v1/auth)

    Note over B: access token expires
    B->>A: POST /auth/refresh (cookie)
    A->>P: look up hash, mark used, issue a new one
    A-->>B: new access + new refresh

    Note over B,P: an attacker replays the old refresh token
    B->>A: POST /auth/refresh (already rotated)
    A->>P: token already used -> revoke the whole family
    A-->>B: 401, everyone signs in again
```

Reuse detection is the reason rotation is worth the complexity. A stolen refresh
token used once is invisible; used twice, it revokes the family and tells you it
happened.

## Why Mermaid

These render on GitHub, diff in review, and are edited in the same commit as the
code they describe. An exported PNG is correct on the day it is exported.
