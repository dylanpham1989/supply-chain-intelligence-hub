#!/usr/bin/env bash
# Creates the local cluster and the two add-ons the manifests assume:
# an ingress controller to reach the app, and metrics-server so the HPA has
# something to read. Without metrics-server an HPA sits at <unknown> forever.
set -euo pipefail

CLUSTER=${CLUSTER:-scih}
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

if kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
    echo "cluster $CLUSTER already exists"
    # The cluster can outlive its kubeconfig entry, for example after the
    # docker daemon is restarted. Writing it again is cheap and idempotent.
    kind export kubeconfig --name "$CLUSTER"
else
    kind create cluster --name "$CLUSTER" --config "$ROOT/infra/k8s/kind-config.yaml"
fi

kubectl config use-context "kind-$CLUSTER"

kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.0/deploy/static/provider/kind/deploy.yaml
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.7.2/components.yaml

# kind's kubelet serves its metrics with a self-signed certificate, and
# metrics-server will not scrape it without this. The flag is a local
# concession, not something to carry into a real cluster.
kubectl patch deployment metrics-server -n kube-system --type=json \
    -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'

# `kubectl wait` fails outright when the resource does not exist yet, and the
# apply above only submits it. Wait for it to appear first.
for _ in $(seq 1 30); do
    kubectl get deployment ingress-nginx-controller -n ingress-nginx >/dev/null 2>&1 && break
    sleep 2
done

kubectl rollout status deployment/ingress-nginx-controller -n ingress-nginx --timeout=600s
kubectl rollout status deployment/metrics-server -n kube-system --timeout=300s

echo "cluster ready. next: make kind-deploy"
