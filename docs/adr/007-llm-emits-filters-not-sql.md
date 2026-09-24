# ADR 007: A rule-based router, and a model that emits filters rather than SQL

Date: 2026-09-23
Status: Accepted

## Context

Two kinds of question arrive. "What is the penalty for late delivery?" is
answered from documents. "Show late deliveries to the EU in Q1" is answered from
shipment rows. A single retrieval path answers the second one badly, because the
answer is an aggregate over structured data that no chunk contains.

## Decision

A rule-based intent router chooses between the two paths. On the structured
path the model produces a JSON object that a Pydantic model with
`extra="forbid"` validates, and the application turns that into SQL. The model
never produces SQL.

## Alternatives considered

| Option | Why not |
|---|---|
| Let the model write SQL | An injection surface where the payload is the query itself. Read-only roles and statement filters reduce the blast radius, they do not remove it |
| An LLM classifier for routing | Slower, costs money, non-deterministic on a decision that a dozen patterns settle, and much harder to test |
| One retrieval path for everything | Aggregates over hundreds of rows are not in any chunk, so the answer is a guess |

## Consequences

Positive: the worst case of a bad model output is a filter that fails validation
and a fallback to retrieval. Routing is deterministic and unit tested. The
structured path costs one small model call, or none when the rule-based
extractor is enough.

Negative: the router's rules need maintaining as question shapes broaden, and a
question that straddles both kinds gets one path. The filter schema limits what
can be asked to what the schema can express.

Revisit when: the rules stop covering the questions people actually ask, which
is visible as fallback rate in `rag_queries_total{route_type=...}`.
