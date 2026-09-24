# ADR 002: Shared schema multi-tenancy with row-level security

Date: 2026-09-22
Status: Accepted

## Context

Several companies use the same deployment and must never see each other's data.
The isolation has to survive an ordinary mistake: a forgotten `WHERE tenant_id`
in a new query, a repository method written in a hurry, a raw SQL report.

## Decision

One schema, a `tenant_id` column on every tenant-owned table, and Postgres
row-level security with `ENABLE` and `FORCE`. The application connects as a role
that owns nothing and cannot bypass RLS, and each transaction sets
`app.tenant_id` from a signed token claim.

## Alternatives considered

| Option | Why not |
|---|---|
| Schema per tenant | Migrations run N times and get half applied; connection pools fragment; 500 tenants means 500 schemas to keep identical |
| Database per tenant | Strongest isolation, highest cost per tenant, and cross-tenant analytics becomes N queries |
| Application-level filtering only | One forgotten predicate is a data breach, and code review is the only thing standing between you and it |

## Consequences

Positive: the guarantee lives in the database, below every ORM, script and
psql session. A query that forgets its predicate returns nothing rather than
everything. Tests prove it by asking for another tenant's rows and getting none.

Negative: RLS costs a planning-time policy check per query, and `SET LOCAL`
makes the transaction boundary part of the security model, so a connection
reused without it is a bug. Noisy neighbours share the same tables and indexes.

Revisit when: a customer contractually requires physical separation, or one
tenant's rows dominate the table enough that partitioning by `tenant_id` becomes
the cheaper way to keep the indexes useful.
