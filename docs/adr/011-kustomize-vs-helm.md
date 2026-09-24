# ADR 011: Kustomize for deployment, not Helm

Date: 2026-09-24
Status: Accepted

## Context

Three environments need the same workloads with different replica counts,
images, secrets and datastore endpoints. The two usual tools are Helm, which
renders Go templates, and Kustomize, which patches plain YAML.

## Decision

Kustomize, through `kubectl apply -k`.

## Consequences

The manifests in `infra/k8s/base` are valid Kubernetes YAML that can be read
directly, applied directly and diffed against a live cluster. A Helm chart of
the same thing is a template: reading it means rendering it first, and a broken
`{{ if }}` produces YAML that is invalid in a way the template does not show.

Kustomize also needs nothing installed. It is part of kubectl.

What is given up is templating. There is no conditional inclusion of a resource,
no loop over a list of environments, and no packaging: this project cannot be
handed to someone else as a chart to install with their own values. That is the
case where Helm is the right answer, and it is not this case. The distinction is
whether the software is deployed by its authors or distributed to strangers.

Two smaller costs: `secretGenerator` normally appends a content hash to the
Secret name so that a change rolls the pods, which is disabled here because the
base refers to the Secret by a fixed name; the deploy script restarts the
deployments instead. And Kustomize refuses to read files above its own
directory, so the Postgres init SQL is applied by the deploy script rather than
copied into the overlay, which would have given the role grants two homes.
