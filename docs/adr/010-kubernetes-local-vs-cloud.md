# ADR 010: Prove the Kubernetes work on kind, not on EKS

Date: 2026-09-24
Status: Accepted

## Context

The deployment target described by this project is EKS. Running one costs money
whether or not anyone is looking at it: the control plane is about 73 dollars a
month, a NAT gateway another 33, and the smallest usable RDS and ElastiCache
pair takes the total to roughly 150 to 250 dollars a month. This is a portfolio
project with no revenue and no users.

The alternatives are to run it anyway for a while, to write manifests that were
never applied to anything, or to run them on a local cluster.

## Decision

The manifests run on a local kind cluster, and the AWS infrastructure stays as
Terraform that is formatted, validated and scanned in CI but never applied.

kind over minikube or k3d because it uses kubeadm the same way a real cluster
does, starts fastest in CI, and `kind load docker-image` puts a locally built
image in front of the kubelet without a registry.

## Consequences

The manifests are executed, not decorative: probes fire, the migration Job
completes before the rollout, the HPA reads real metrics from metrics-server,
and a smoke test drives the deployed system end to end. That is the evidence
that matters, and it is the same evidence CI produces on every push.

What is not proven: anything cloud specific. Load balancer provisioning, IRSA,
the RDS parameter group and ExternalSecret syncing are written and validated but
never exercised. NetworkPolicy is applied but not enforced, because the default
kind CNI ignores it.

The honest version of this is written down in `docs/deployment.md` rather than
left for someone to find. Saying "validated and scanned, not applied, here is
what that costs" is a defensible answer. Implying it ran on AWS is not.
