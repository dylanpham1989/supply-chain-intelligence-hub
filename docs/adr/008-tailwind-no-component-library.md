# ADR 008: Tailwind and a handful of local components, not a component library

Date: 2026-09-23
Status: Accepted

## Context

The UI is six pages: tables, filters, charts, a few panels and a form. It needs
to look deliberate without a design system budget.

## Decision

Tailwind v4 for styling, Recharts for charts, and a small set of components
written in the repository (`SidePanel`, table primitives, form controls).

## Alternatives considered

| Option | Why not |
|---|---|
| MUI or Ant Design | A large dependency and a design language to fight, for six pages. Bundle cost is real and the escape hatches are worse than writing the component |
| shadcn/ui | Closest alternative, and reasonable. It brings Radix and a generator; at this size copying the three components actually needed was less machinery |
| Plain CSS modules | More code for the same result, and no constraint on spacing or colour |

## Consequences

Positive: the initial bundle is 92 kB gzipped with charts split into the
dashboard's own chunk. Nothing is styled by overriding a library's defaults.
The components that exist do exactly what this app needs.

Negative: accessibility is on us. The side panel needed focus management,
Escape handling and a dialog role written by hand, and a library would have had
them. A seventh and eighth page will need components that do not exist yet.

Revisit when: the component count passes roughly fifteen, or accessibility
requirements go beyond what is reasonable to hand roll.
