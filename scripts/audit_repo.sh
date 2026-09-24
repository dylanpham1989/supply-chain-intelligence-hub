#!/usr/bin/env bash
# Everything that should be true of this repository before it is shown to
# anyone. Runs the assistant-trace check plus the hygiene checks that are easy
# to forget: stray debug output, editor leftovers, committed OS metadata.
set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

fails=0

report() {
    local name=$1 hits=$2
    if [[ -n "$hits" ]]; then
        echo "FAIL $name"
        echo "$hits" | sed 's/^/     /'
        fails=$((fails + 1))
    else
        echo "ok   $name"
    fi
}

bash scripts/check_ai_traces.sh || fails=$((fails + 1))

report "no os metadata committed" \
    "$(git ls-files | grep -E '(^|/)\.DS_Store$|\.orig$|\.rej$|\.bak$' || true)"

report "no debug output in the frontend" \
    "$(git grep -n 'console\.log' -- 'frontend/src/**/*.ts' 'frontend/src/**/*.tsx' || true)"

report "no debug output in the backend" \
    "$(git grep -nE '(^|[^.\w])(breakpoint\(\)|pdb\.set_trace)' -- 'backend/**/*.py' || true)"

# A TODO is fine in a note to a reader. A TODO that says the code is unfinished
# is not something to hand to someone reading the repository cold.
report "no unfinished markers" \
    "$(git grep -nE 'TODO: (implement|fix|finish)|FIXME|XXX' -- 'backend' 'frontend/src' 'infra' || true)"

report "lockfiles are committed" \
    "$(for f in backend/uv.lock frontend/package-lock.json; do
         git ls-files --error-unmatch "$f" >/dev/null 2>&1 || echo "missing $f"
       done)"

report "no secrets outside the examples" \
    "$(git ls-files | grep -E '(^|/)\.env$|secret\.env$' || true)"

# A history where every commit lands in the same ten minutes says the work was
# not done the way the commits claim. This only reports; it does not judge.
echo
echo "commits per hour, busiest first:"
git log --format='%ad' --date=format:'%Y-%m-%d %H' | sort | uniq -c | sort -rn | head -5 | sed 's/^/     /'

echo
if [[ $fails -gt 0 ]]; then
    echo "audit_repo: $fails check(s) failed"
    exit 1
fi
echo "audit_repo: clean"
