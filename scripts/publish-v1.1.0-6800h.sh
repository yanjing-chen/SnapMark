#!/usr/bin/env bash
# SnapMark v1.1.0 release from Ryzen 6800H Ubuntu. Requires GitHub CLI authentication.
# Safe order: back up refs -> normal main push -> main CI success -> release tag ->
# tagged Actions build+publish success -> asset verification -> prune remote side branches.
set -Eeuo pipefail

REPO='yanjing-chen/SnapMark'
TAG='v1.1.0'
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -f "$ROOT/snapmark/app.py" || ! -f "$ROOT/.github/workflows/appimage.yml" ]]; then
  echo 'ERROR: full SnapMark source tree not found next to release script.' >&2
  exit 1
fi
if [[ -d "$HOME/下载" ]]; then BASE="$HOME/下载"; else BASE="$HOME/Downloads"; fi
mkdir -p "$BASE/SnapMark-release-backups"
STAMP="$(date +%Y%m%d-%H%M%S)"
WORK="$BASE/SnapMark-1.1.0-publish-$STAMP"
BACKUP="$BASE/SnapMark-release-backups/SnapMark-before-v1.1.0-$STAMP.bundle"
LOG="$BASE/SnapMark-release-v1.1.0-$STAMP.log"
exec > >(tee -a "$LOG") 2>&1
trap 'echo "ERROR near line $LINENO. Log: $LOG" >&2' ERR

echo '===== SnapMark v1.1.0 local GitHub release ====='
echo "SOURCE=$ROOT"
echo "WORK=$WORK"
echo "BACKUP=$BACKUP"
echo "LOG=$LOG"

for c in git gh python3; do
  command -v "$c" >/dev/null || { echo "ERROR: $c missing" >&2; exit 1; }
done
if ! gh auth status >/dev/null 2>&1; then
  echo 'ERROR: GitHub CLI not authenticated. Run: gh auth login -p https -w' >&2
  exit 1
fi
USER_LOGIN="$(gh api user --jq .login)"
if [[ "$USER_LOGIN" != 'yanjing-chen' ]]; then
  echo "ERROR: logged in as $USER_LOGIN, expected yanjing-chen" >&2
  exit 1
fi
REPO_FULL="$(gh repo view "$REPO" --json nameWithOwner --jq .nameWithOwner)"
if [[ "$REPO_FULL" != "$REPO" ]]; then
  echo "ERROR: unexpected repository $REPO_FULL" >&2
  exit 1
fi
DEFAULT_BRANCH="$(gh repo view "$REPO" --json defaultBranchRef --jq .defaultBranchRef.name)"
if [[ "$DEFAULT_BRANCH" != 'main' ]]; then
  echo "ERROR: GitHub default branch is $DEFAULT_BRANCH, expected main. No push performed." >&2
  exit 1
fi
if gh release view "$TAG" -R "$REPO" >/dev/null 2>&1; then
  echo "ERROR: Release $TAG already exists; refusing duplicate publication." >&2
  exit 1
fi
if [[ -n "$(git ls-remote --tags "https://github.com/$REPO.git" "refs/tags/$TAG")" ]]; then
  echo "ERROR: Git tag $TAG exists remotely; refusing to overwrite." >&2
  exit 1
fi
if [[ -e "$WORK" ]]; then echo "ERROR: worktree exists: $WORK" >&2; exit 1; fi

# Validate the exact source BEFORE changing a remote branch.
cd "$ROOT"
python3 - <<'PY'
from snapmark import __version__
assert __version__ == '1.1.0', __version__
print(f'Source release version: {__version__}')
PY
/usr/bin/python3 -m compileall -q snapmark tests
/usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 scripts/make-source-archive.py

# GitHub credentials are applied only to the user's local Git configuration.
gh auth setup-git

echo '===== 1. Clone and back up all existing Git refs ====='
git clone "https://github.com/$REPO.git" "$WORK"
git -C "$WORK" fetch --prune origin '+refs/heads/*:refs/remotes/origin/*' --tags
if ! git -C "$WORK" show-ref --verify --quiet refs/remotes/origin/main; then
  echo 'ERROR: origin/main does not exist' >&2
  exit 1
fi
printf 'Existing remote branches:\n'
git ls-remote --heads "https://github.com/$REPO.git" | sed 's#refs/heads/##'
git -C "$WORK" bundle create "$BACKUP" --all
git -C "$WORK" bundle verify "$BACKUP"
sha256sum "$BACKUP" > "$BACKUP.sha256"
echo "Safeguard: $BACKUP"

echo '===== 2. Prepare main using current history (NO force push) ====='
git -C "$WORK" checkout -B main origin/main
OLD_MAIN="$(git -C "$WORK" rev-parse HEAD)"
echo "Previous main: $OLD_MAIN"
# This is a fresh clone in a uniquely named publish directory, not the user's working tree.
find "$WORK" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf -- {} +
cp -a "$ROOT/." "$WORK/"
# Never accidentally stage an embedded Git repository from the extracted full source.
if [[ -e "$ROOT/.git" ]]; then
  echo 'ERROR: source archive unexpectedly contains a .git directory' >&2
  exit 1
fi

git -C "$WORK" config user.name "$(git config --global user.name 2>/dev/null || echo 'yanjing-chen')"
git -C "$WORK" config user.email "$(git config --global user.email 2>/dev/null || echo 'yanjing_chen@qq.com')"
git -C "$WORK" add -A
git -C "$WORK" diff --cached --check
if git -C "$WORK" diff --cached --quiet; then
  echo 'ERROR: no changes to publish. Stop instead of creating an empty release commit.' >&2
  exit 1
fi
git -C "$WORK" commit -m 'Release SnapMark v1.1.0 with built-in Ollama OCR'
COMMIT="$(git -C "$WORK" rev-parse HEAD)"
echo "New main commit: $COMMIT"
# Remote concurrent changes cause this normal push to fail; no force option is used.
git -C "$WORK" push origin HEAD:refs/heads/main
MAIN_NOW="$(git -C "$WORK" ls-remote origin refs/heads/main | cut -f1)"
if [[ "$MAIN_NOW" != "$COMMIT" ]]; then
  echo "ERROR: main does not point to release commit ($MAIN_NOW != $COMMIT)" >&2
  exit 1
fi

echo '===== 3. Wait for main Actions to pass ====='
wait_for_run() {
  local ref="$1" sha="$2" run_id='' attempt
  for attempt in $(seq 1 72); do
    run_id="$(gh run list -R "$REPO" --workflow appimage.yml --commit "$sha" \
      --event push --limit 50 --json databaseId,headBranch,headSha \
      --jq ".[] | select(.headSha == \"$sha\" and .headBranch == \"$ref\") | .databaseId" 2>/dev/null | head -n 1 || true)"
    if [[ "$run_id" =~ ^[0-9]+$ ]]; then break; fi
    if (( attempt % 6 == 0 )); then echo "Waiting for Actions for $ref ($attempt)..."; fi
    sleep 5
  done
  if [[ ! "$run_id" =~ ^[0-9]+$ ]]; then
    echo "ERROR: no Actions run for $ref / $sha. Check https://github.com/$REPO/actions" >&2
    return 1
  fi
  echo "Watching GitHub Actions run $run_id for $ref"
  gh run watch "$run_id" -R "$REPO" --compact --exit-status
}
wait_for_run main "$COMMIT"

echo '===== 4. Push release tag; tagged Actions creates GitHub Release ====='
git -C "$WORK" tag -a "$TAG" -m 'SnapMark v1.1.0 official release' "$COMMIT"
git -C "$WORK" push origin "refs/tags/$TAG:refs/tags/$TAG"
wait_for_run "$TAG" "$COMMIT"

echo '===== 5. Verify GitHub Release and all required assets ====='
release_assets="$(gh release view "$TAG" -R "$REPO" --json assets --jq '.assets[].name')"
printf '%s\n' "$release_assets"
for asset in 'SnapMark-1.1.0-x86_64.AppImage' 'SnapMark-1.1.0-Full-Source.zip' 'SHA256SUMS.txt'; do
  if ! grep -Fxq -- "$asset" <<< "$release_assets"; then
    echo "ERROR: Release asset missing: $asset. No branches will be deleted." >&2
    exit 1
  fi
done

echo '===== 6. Delete remote non-main branches only after Release verification ====='
# Includes release/snapmark-v1.0.0 and any other remote branch; tags are untouched.
mapfile -t branches < <(git -C "$WORK" ls-remote --heads origin | awk '{sub(/^refs\/heads\//,"",$2); print $2}')
failed=0
for branch in "${branches[@]}"; do
  if [[ "$branch" == main ]]; then continue; fi
  if [[ -z "$branch" ]]; then continue; fi
  echo "Deleting remote branch: $branch"
  if ! git -C "$WORK" push origin --delete "$branch"; then
    echo "WARNING: could not delete branch $branch (may be protected)" >&2
    failed=1
  fi
done
mapfile -t remaining < <(git -C "$WORK" ls-remote --heads origin | awk '{sub(/^refs\/heads\//,"",$2); print $2}')
printf 'Remaining remote branches:\n%s\n' "${remaining[*]}"
if (( failed != 0 )) || (( ${#remaining[@]} != 1 )) || [[ "${remaining[0]}" != main ]]; then
  echo 'WARNING: Release is published but branch cleanup incomplete.' >&2
  echo "Backup is safe: $BACKUP" >&2
  exit 1
fi

echo '===== RELEASE COMPLETE ====='
echo "main=$COMMIT"
echo "RELEASE=https://github.com/$REPO/releases/tag/$TAG"
echo "SOURCE_BACKUP=$BACKUP"
echo "LOCAL_GIT_WORKTREE=$WORK"
echo "LOG=$LOG"
