# ADR 005: Offset pagination, with a documented ceiling

Date: 2026-09-23
Status: Accepted

## Context

Every list endpoint pages. The UI shows page numbers and lets a user jump to a
page, which is what product wanted for a table of shipments.

## Decision

`LIMIT` and `OFFSET`, with a page size capped at 100 and a total count returned
alongside.

## Alternatives considered

| Option | Why not |
|---|---|
| Keyset (seek) pagination | Correct and fast at any depth, but cannot jump to page 40 and cannot show a total without a second query. The UI asks for both |
| Cursor tokens | Same trade as keyset with an opaque token; still no page numbers |

## Consequences

Positive: simple, supports the UI the product has, and a total count makes the
table honest about how much is there.

Negative: `OFFSET 50000` makes Postgres walk 50,000 rows before discarding them,
and `COUNT(*)` scans. At demo scale (a few hundred rows per tenant) neither is
measurable. Past roughly 100,000 rows per tenant both become the slowest part of
the request.

Revisit when: a tenant passes about 100,000 shipments, or page-depth latency
shows up in `http_request_duration_seconds` for the list routes. The fix is
keyset ordering on `(created_at, id)` with an approximate count.
