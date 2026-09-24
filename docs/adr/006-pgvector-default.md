# ADR 006: pgvector by default, with the vector store behind an interface

Date: 2026-09-23
Status: Accepted

## Context

Retrieval needs vector similarity search, scoped per tenant, over chunks that
already live in Postgres as rows.

## Decision

pgvector with an HNSW index, behind a `VectorStore` protocol that a hosted
service can implement instead.

## Alternatives considered

| Option | Why not |
|---|---|
| Pinecone | Another system to run, pay for and keep in step, and tenant isolation becomes a second thing to prove. Worth it at a scale this is not at |
| Qdrant or Milvus self-hosted | Same duplication of state, plus the operational load lands on us |
| FAISS in process | No persistence, no concurrent writers, and every replica holds its own copy |

## Consequences

Positive: the vector sits on the chunk row, so the same row-level security
policy covers it and there is no second system to keep consistent. A document
deleted in Postgres cannot leave orphaned vectors somewhere else. One backup
covers everything.

Negative: HNSW in Postgres does not scale the way a dedicated engine does, and
a highly selective tenant filter degrades the index walk because the filter is
applied after the graph traversal. Index builds hold memory.

Revisit when: a tenant's chunk count makes recall or latency unacceptable, or
the corpus outgrows what one Postgres instance should hold. The adapter is the
seam to swap.
