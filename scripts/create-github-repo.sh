#!/usr/bin/env bash
# RUN ON: AMD Ryzen 7 6800H · Ubuntu GNOME 50 Wayland.
# Safe new-repository creation; no reset, force-push, or rewriting existing history.
set -euo pipefail
REPO='yanjing-chen/SnapMark'
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
for program in gh git; do
  command -v "$program" >/dev/null || { echo "Missing required tool: $program" >&2; exit 1; }
done
if ! gh auth status >/dev/null 2>&1; then
  echo 'GitHub CLI is not authenticated. Run: gh auth login' >&2
  exit 1
fi
LOGIN="$(gh api user --jq .login)"
if [[ "$LOGIN" != 'yanjing-chen' ]]; then
  echo "Refusing to create repository on the wrong account: $LOGIN" >&2
  exit 1
fi
if gh repo view "$REPO" >/dev/null 2>&1; then
  echo "Repository $REPO already exists. Nothing was changed." >&2
  exit 1
fi
if [[ -e .git ]]; then
  echo 'The current directory already has a Git repository; refusing to reinitialize it.' >&2
  exit 1
fi
if [[ -n "$(git status --porcelain 2>/dev/null || true)" ]] && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo 'Project is inside a pre-existing worktree; refusing to act.' >&2
  exit 1
fi
AUTHOR_NAME="$(git config user.name || true)"
AUTHOR_EMAIL="$(git config user.email || true)"
if [[ -z "$AUTHOR_NAME" ]]; then AUTHOR_NAME="$LOGIN"; fi
if [[ -z "$AUTHOR_EMAIL" ]]; then
  AUTHOR_EMAIL="$(gh api user/emails --jq '[.[] | select(.primary == true and .verified == true) | .email][0] // empty' 2>/dev/null || true)"
fi
if [[ -z "$AUTHOR_EMAIL" ]]; then
  USER_ID="$(gh api user --jq .id)"
  AUTHOR_EMAIL="${USER_ID}+${LOGIN}@users.noreply.github.com"
fi
printf 'GitHub account: %s\nNew repository: %s\nSource: %s\n' "$LOGIN" "$REPO" "$ROOT"
read -r -p 'Create PUBLIC repository and push SnapMark main? [y/N] ' reply
if [[ "$reply" != 'y' && "$reply" != 'Y' ]]; then
  echo 'Cancelled without changes.'
  exit 0
fi
git init -b main
git config user.name "$AUTHOR_NAME"
git config user.email "$AUTHOR_EMAIL"
git add -A
git commit -m 'Initial SnapMark GTK4 screenshot annotation prototype'
gh repo create "$REPO" --public --source . --remote origin --push
printf '\nCreated repository. Check Actions at:\nhttps://github.com/%s/actions\n' "$REPO"
