#!/usr/bin/env bash
# Upload project to GitHub: https://github.com/Laniccc/Evidence-first-Travel-Intelligence-Agent.git
# Usage:
#   bash upload_to_github.sh
#   bash upload_to_github.sh "custom commit message"
#   DRY_RUN=1 bash upload_to_github.sh

set -euo pipefail

REMOTE_URL="${REMOTE_URL:-https://github.com/Laniccc/Evidence-first-Travel-Intelligence-Agent.git}"
BRANCH="${BRANCH:-main}"
MESSAGE="${1:-init: Evidence-first Travel Intelligence Agent MVP}"
DRY_RUN="${DRY_RUN:-0}"

cd "$(dirname "$0")"
echo "Project: $(pwd)"

if [[ -f apps/agent-python/.env ]] || [[ -f .env ]]; then
  echo "WARNING: .env exists locally and is ignored by git (will NOT be uploaded)."
fi

run_git() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[dry-run] git $*"
    return 0
  fi
  git "$@"
}

command -v git >/dev/null || { echo "git not found"; exit 1; }

if [[ ! -d .git ]]; then
  echo "Initializing git repository..."
  run_git init
  run_git branch -M "$BRANCH"
fi

if run_git remote 2>/dev/null | grep -qx origin; then
  echo "Updating remote origin -> $REMOTE_URL"
  run_git remote set-url origin "$REMOTE_URL"
else
  echo "Adding remote origin -> $REMOTE_URL"
  run_git remote add origin "$REMOTE_URL"
fi

run_git add -A
run_git status

if [[ "$DRY_RUN" != "1" ]]; then
  if [[ -z "$(git status --porcelain)" ]]; then
    echo "No changes to commit."
  else
    run_git commit -m "$MESSAGE"
  fi
fi

echo "Pushing to origin/$BRANCH ..."
if [[ "$DRY_RUN" == "1" ]]; then
  echo "[dry-run] git push -u origin $BRANCH"
  echo "Dry run complete."
  exit 0
fi

run_git push -u origin "$BRANCH"
echo "Done. Repository: $REMOTE_URL"
