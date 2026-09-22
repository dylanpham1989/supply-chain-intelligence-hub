#!/usr/bin/env bash
# Fails if AI-assistant tooling artefacts or generated-text tells are present in
# tracked files, commit metadata, or anywhere in the history.
set -uo pipefail

SELF="scripts/check_ai_traces.sh"
fail=0

report() {
  printf '  %s\n' "$1"
  fail=1
}

# 1. Forbidden strings in tracked file contents.
CONTENT_PATTERNS=(
  'co-authored-by: claude'
  'generated with .*claude'
  'claude code'
  'anthropic.com/claude'
  'noreply@anthropic'
  'as an ai language model'
  "here's the updated"
  'certainly! '
)
for pattern in "${CONTENT_PATTERNS[@]}"; do
  if hits=$(git grep -nIiE -e "$pattern" -- . ":!$SELF" 2>/dev/null) && [ -n "$hits" ]; then
    report "content match: $pattern"
    printf '%s\n' "$hits" | head -5 | sed 's/^/    /'
  fi
done

# 2. Robot emoji in tracked files.
if hits=$(git grep -nI $'\xf0\x9f\xa4\x96' -- . ":!$SELF" 2>/dev/null) && [ -n "$hits" ]; then
  report "robot emoji in tracked files"
  printf '%s\n' "$hits" | head -5 | sed 's/^/    /'
fi

# 3. Em dash: a reliable tell of generated prose, and never needed in source.
if hits=$(git grep -nI -e $'\xe2\x80\x94' -- '*.md' '*.py' '*.ts' '*.tsx' '*.yml' '*.yaml' '*.tf' ":!$SELF" 2>/dev/null) && [ -n "$hits" ]; then
  report "em dash in tracked files"
  printf '%s\n' "$hits" | head -5 | sed 's/^/    /'
fi

# 4. Tooling paths that must never be tracked.
for path in .claude CLAUDE.md .cursorrules .cursor .aider.conf.yml .windsurfrules plans; do
  if git ls-files --error-unmatch "$path" >/dev/null 2>&1; then
    report "tracked tooling path: $path"
  fi
done

# 5. Same paths, anywhere in the history (including files later deleted).
if hits=$(git log --all --diff-filter=A --name-only --format='' 2>/dev/null \
            | sort -u | grep -iE '(^|/)(\.claude|CLAUDE\.md|\.cursor|\.aider|plans/)') && [ -n "$hits" ]; then
  report "tooling path present in history"
  printf '%s\n' "$hits" | head -5 | sed 's/^/    /'
fi

# 6. Commit metadata across the whole history.
if git log --all --format='%an%x09%ae%x09%cn%x09%ce%x09%s%x09%b' 2>/dev/null \
     | grep -qiE 'claude|anthropic|copilot|codeium|cursor\.(so|com)'; then
  report "assistant reference in commit metadata"
  git log --all --format='%h %an <%ae> %s' | grep -iE 'claude|anthropic|copilot' | head -5 | sed 's/^/    /'
fi

if [ "$fail" -eq 0 ]; then
  echo "check_ai_traces: clean"
else
  echo "check_ai_traces: FAILED"
  exit 1
fi
