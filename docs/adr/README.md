# Architecture decision records

One page per decision that would otherwise have to be re-argued from memory.
Format is Nygard's, with one addition: every record ends with **Revisit when**,
a condition that would make the decision wrong. A decision without one is a
preference.

| # | Decision | Date |
|---|---|---|
| [001](001-monorepo-two-entrypoints.md) | One repository, one Python project, two entrypoints | 2026-09-22 |
| [002](002-shared-schema-rls.md) | Shared schema multi-tenancy with row-level security | 2026-09-22 |
| [003](003-jwt-refresh-rotation.md) | Short access tokens in memory, rotating refresh tokens in a cookie | 2026-09-22 |
| [004](004-arq-over-celery.md) | ARQ for background jobs, not Celery | 2026-09-22 |
| [005](005-offset-pagination.md) | Offset pagination, with a documented ceiling | 2026-09-23 |
| [006](006-pgvector-default.md) | pgvector by default, with the vector store behind an interface | 2026-09-23 |
| [007](007-llm-emits-filters-not-sql.md) | A rule-based router, and a model that emits filters rather than SQL | 2026-09-23 |
| [008](008-tailwind-no-component-library.md) | Tailwind and local components, not a component library | 2026-09-23 |
| [009](009-no-risk-classifier.md) | No shipment risk classifier | 2026-09-24 |
| [010](010-kubernetes-local-vs-cloud.md) | Prove the Kubernetes work on kind, not on EKS | 2026-09-24 |
| [011](011-kustomize-vs-helm.md) | Kustomize for deployment, not Helm | 2026-09-24 |
