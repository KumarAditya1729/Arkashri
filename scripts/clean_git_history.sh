#!/usr/bin/env bash

set -euo pipefail

if ! command -v git-filter-repo >/dev/null 2>&1; then
  echo "git-filter-repo is required. Install it first (for example: brew install git-filter-repo)." >&2
  exit 1
fi

cat <<'EOF'
About to rewrite git history and permanently remove local artifact files.
Make sure everyone has stopped pushing to this branch and that you have a fresh backup/clone.
EOF

git filter-repo --force \
  --path-glob '*.db' \
  --path-glob '*.db-*' \
  --path-glob '*.sqlite' \
  --path-glob '*.sqlite3' \
  --path-glob '*.sqlite-shm' \
  --path-glob '*.sqlite-wal' \
  --path logs \
  --path-glob '*.log' \
  --path-glob '*.out' \
  --path-glob '*.err' \
  --path-glob '*.pid' \
  --path-glob '*.trace' \
  --path-glob '*.har' \
  --path-glob '.DS_Store' \
  --path test_websocket.html \
  --path run_e2e_local.py \
  --invert-paths

git reflog expire --expire=now --all
git gc --prune=now --aggressive

cat <<'EOF'
History cleanup complete.
Next steps:
  1. Reinstall hooks: ./scripts/install-git-hooks.sh
  2. Force-push safely: git push --force-with-lease origin <branch>
  3. Ask collaborators to re-clone or hard-reset to the rewritten branch tip.
EOF
