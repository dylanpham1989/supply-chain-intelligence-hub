#!/usr/bin/env bash
# Builds the three images, pushes them into the kind node, applies the local
# overlay and waits for it to come up.
set -euo pipefail

CLUSTER=${CLUSTER:-scih}
NS=${NS:-scih}
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

if [[ ! -f infra/k8s/overlays/local/secret.env ]]; then
    cp infra/k8s/overlays/local/secret.env.example infra/k8s/overlays/local/secret.env
    echo "created infra/k8s/overlays/local/secret.env from the example"
fi

echo "==> building images"
docker build -f infra/docker/Dockerfile.api -t scih-api:local .
docker build -f infra/docker/Dockerfile.worker -t scih-worker:local .
docker build -f infra/docker/Dockerfile.web --target runtime -t scih-web:local .

echo "==> loading images into the cluster"
# kind nodes have their own container store, so an image on the host is not an
# image the kubelet can see.
kind load docker-image --name "$CLUSTER" scih-api:local scih-worker:local scih-web:local

echo "==> applying manifests"
kubectl apply -f infra/k8s/base/namespace.yaml
# Generated here rather than by kustomize, which refuses to read files above
# its own directory. This keeps one copy of the role grants.
kubectl create configmap postgres-init -n "$NS" \
    --from-file=00-init.sql=backend/scripts/init-db.sql \
    --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -k infra/k8s/overlays/local

echo "==> waiting for datastores"
kubectl wait -n "$NS" --for=condition=ready pod -l app=postgres --timeout=300s
kubectl wait -n "$NS" --for=condition=ready pod -l app=redis --timeout=180s
kubectl wait -n "$NS" --for=condition=ready pod -l app=minio --timeout=180s

echo "==> waiting for migrations"
# The Job waits for postgres itself, so there is nothing to order here. It is a
# Job rather than an init container because an init container runs once per pod,
# and two api replicas would race each other through alembic.
kubectl wait -n "$NS" --for=condition=complete job/db-migrate --timeout=300s

echo "==> waiting for the application"
kubectl rollout status -n "$NS" deploy/api --timeout=300s
kubectl rollout status -n "$NS" deploy/worker --timeout=300s
kubectl rollout status -n "$NS" deploy/web --timeout=180s

echo "==> seeding demo data"
kubectl exec -n "$NS" deploy/api -- python -m scripts.seed_data

kubectl get pods -n "$NS"
echo "app on http://localhost:8081"
