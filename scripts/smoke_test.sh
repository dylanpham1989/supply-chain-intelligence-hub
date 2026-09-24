#!/usr/bin/env bash
# One definition of "the system works", used by the local stack, by kind and by
# CI. Upload a contract, wait for it to be indexed, ask a question about it and
# require a grounded answer back.
set -euo pipefail

BASE_URL=${BASE_URL:-http://localhost:8000}
TENANT=${TENANT:-acme-logistics}
EMAIL=${EMAIL:-admin@acme.test}
PASSWORD=${PASSWORD:-Demo1234!}
SAMPLE=${SAMPLE:-data/samples/contract_acme_supply_2026.pdf}
INDEX_TIMEOUT_S=${INDEX_TIMEOUT_S:-180}

fail() { echo "smoke: $1" >&2; exit 1; }

json() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)"; }

echo "==> readiness"
curl -fsS "$BASE_URL/health/ready" >/dev/null || fail "not ready"

echo "==> login"
TOKEN=$(curl -fsS -X POST "$BASE_URL/api/v1/auth/login" \
    -H 'content-type: application/json' \
    -d "{\"tenant_slug\":\"$TENANT\",\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" \
    | json "d['access_token']") || fail "login failed"

echo "==> upload"
DOC_ID=$(curl -fsS -X POST "$BASE_URL/api/v1/documents" \
    -H "Authorization: Bearer $TOKEN" \
    -F "file=@$SAMPLE" -F "doc_type=contract" \
    | json "d['document_id']") || fail "upload failed"

echo "==> waiting for $DOC_ID to be indexed"
deadline=$((SECONDS + INDEX_TIMEOUT_S))
status=""
while [[ $SECONDS -lt $deadline ]]; do
    status=$(curl -fsS "$BASE_URL/api/v1/documents/$DOC_ID" \
        -H "Authorization: Bearer $TOKEN" | json "d['status']")
    [[ "$status" == "indexed" ]] && break
    [[ "$status" == "failed" ]] && fail "ingestion failed"
    sleep 3
done
[[ "$status" == "indexed" ]] || fail "still $status after ${INDEX_TIMEOUT_S}s"

echo "==> asking"
ANSWER=$(curl -fsS -X POST "$BASE_URL/api/v1/ask" \
    -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
    -d '{"question":"What is the penalty for late delivery?"}')

echo "$ANSWER" | json "d['answer']" | grep -q . || fail "empty answer"
CITATIONS=$(echo "$ANSWER" | json "len(d.get('citations') or [])")
# An answer with no citation is the failure this project exists to avoid: the
# model talking rather than reading.
[[ "$CITATIONS" -gt 0 ]] || fail "answer had no citations"

echo "smoke: ok, answer cited $CITATIONS source(s)"
