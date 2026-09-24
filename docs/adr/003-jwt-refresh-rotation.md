# ADR 003: Short access tokens in memory, rotating refresh tokens in a cookie

Date: 2026-09-22
Status: Accepted

## Context

A browser application needs to stay signed in without handing a long-lived
credential to any script that runs on the page.

## Decision

A 15 minute access token, HS256, kept in a JavaScript variable and never in
`localStorage`. A 7 day refresh token in an httpOnly, SameSite=strict cookie
scoped to `/api/v1/auth`, stored server side as a sha256 hash, and rotated on
every use. Reusing a rotated token revokes the entire family.

## Alternatives considered

| Option | Why not |
|---|---|
| Access token in localStorage | Any injected script can read it, and it survives the tab |
| Server sessions in Redis | Simpler to revoke, but a lookup on every request and sticky infrastructure the stateless services do not otherwise need |
| Long-lived access token, no refresh | Nothing to revoke, and a stolen token is valid for its whole life |
| RS256 | Useful when a third party verifies tokens without calling us; nobody does here, and it adds key distribution |

## Consequences

Positive: a stolen access token expires in minutes. A stolen refresh token is
detectable: when the real client next rotates, the reuse is visible and the
family is revoked, which logs the attacker out too.

Negative: a page reload has no access token and must call refresh first, so the
client needs single-flight logic to avoid a stampede. HS256 means every verifier
holds the signing secret.

Revisit when: a second service needs to verify tokens it did not issue, which is
the point where RS256 and a JWKS endpoint start paying for themselves.
