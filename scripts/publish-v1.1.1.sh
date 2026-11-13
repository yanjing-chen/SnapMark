#!/usr/bin/env bash
# Safe local-push procedure for SnapMark 1.1.1 stable release.
# Never force-push, overwrite existing tags, alter old Releases, or prune branches.
set -Eeuo pipefail
REPO='yanjing-chen/SnapMark'
TAG='v1.1.1'
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ -f "$ROOT/snapmark/app.py" ] && [ -f "$ROOT/scripts/build-deb.sh" ] || {
  echo 'Expected complete source checkout next to this release script.' >&2; exit 1;
}
if [[ -d "$HOME/下载" ]]; then BASE="$HOME/下载"; else BASE="$HOME/Downloads"; fi
mkdir -p "$BASE/SnapMark-release-backups"
STAMP="$(date +%Y%m%d-%H%M%S)"
WORK="$BASE/SnapMark-1.1.1-publish-$STAMP"
BACKUP="$BASE/SnapMark-release-backups/SnapMark-before-$TAG-$STAMP.bundle"
LOG="$BASE/SnapMark-release-$TAG-$STAMP.log"
exec > >(tee -a "$LOG") 2>&1
trap 'echo "Publish stopped at line $LINENO. Log: $LOG" >&2' ERR

echo "===== SnapMark $TAG: AppImage + native DEB release ====="
for c in git gh python3 tar; do command -v "$c" >/dev/null || { echo "Missing $c" >&2; exit 1; }; done
gh auth status
account="$(gh api user --jq .login)"
[[ "$account" == 'yanjing-chen' ]] || { echo "Wrong GitHub account: $account" >&2; exit 1; }
[[ "$(gh repo view "$REPO" --json defaultBranchRef --jq .defaultBranchRef.name)" == main ]] || {
  echo 'main must be the default branch.' >&2; exit 1;
}
if [[ -n "$(git ls-remote --tags "https://github.com/$REPO.git" "refs/tags/$TAG")" ]] || \
    gh release view "$TAG" -R "$REPO" >/dev/null 2>&1; then
  echo "Tag or release $TAG exists: refusing overwrite." >&2
  exit 1
fi
[[ ! -e "$WORK" ]] || { echo "Publish path already exists: $WORK" >&2; exit 1; }
[[ ! -e "$ROOT/.git" ]] || { echo 'Publish input must be extracted complete source ZIP, not a nested Git checkout.' >&2; exit 1; }

cd "$ROOT"
/usr/bin/python3 - <<'PY'
from snapmark import __version__
assert __version__ == '1.1.1', __version__
PY
/usr/bin/python3 -m compileall -q snapmark tests scripts
/usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 scripts/test-packaging.py -v
# Verify the DEB locally, independently of GitHub-hosted Actions.
bash scripts/build-deb.sh
/usr/bin/python3 scripts/make-source-archive.py
gh auth setup-git

echo '===== Clone main and back up all refs ====='
git clone "https://github.com/$REPO.git" "$WORK"
git -C "$WORK" fetch origin --tags
git -C "$WORK" bundle create "$BACKUP" --all
git -C "$WORK" bundle verify "$BACKUP"
sha256sum "$BACKUP" > "$BACKUP.sha256"
git -C "$WORK" checkout -B main origin/main
find "$WORK" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf -- {} +
# Copy full source while excluding generated output and caches.
( cd "$ROOT" && tar --exclude='./.git' --exclude='./build' --exclude='./dist' \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' -cf - . ) | \
  tar -xf - -C "$WORK"
git -C "$WORK" config user.name "$(git config --global user.name 2>/dev/null || echo 'yanjing-chen')"
git -C "$WORK" config user.email "$(git config --global user.email 2>/dev/null || echo 'yanjing_chen@qq.com')"
git -C "$WORK" add -A
git -C "$WORK" diff --cached --check
if git -C "$WORK" diff --cached --quiet; then
  echo 'No changes to main; refusing an empty release commit.' >&2; exit 1
fi
git -C "$WORK" commit -m 'Release SnapMark v1.1.1 (AppImage + native DEB)'
COMMIT="$(git -C "$WORK" rev-parse HEAD)"
git -C "$WORK" push origin HEAD:refs/heads/main
[[ "$(git -C "$WORK" ls-remote origin refs/heads/main | cut -f1)" == "$COMMIT" ]]

find_run() {
  local ref="$1" sha="$2" run_id='' n
  for n in $(seq 1 72); do
    run_id="$(gh run list -R "$REPO" --workflow appimage.yml --commit "$sha" \
       --event push --limit 50 --json databaseId,headBranch,headSha \
       --jq ".[] | select(.headSha == \"$sha\" and .headBranch == \"$ref\") | .databaseId" \
       2>/dev/null | head -n 1 || true)"
    [[ "$run_id" =~ ^[0-9]+$ ]] && break
    sleep 5
  done
  [[ "$run_id" =~ ^[0-9]+$ ]] || { echo "Missing CI for $ref ($sha)" >&2; return 1; }
  echo "Watching $ref run ID $run_id"
  gh run watch "$run_id" -R "$REPO" --compact --exit-status
}

echo '===== Wait for main package CI ====='
find_run main "$COMMIT"
echo '===== Tag only after main Actions succeeds ====='
git -C "$WORK" tag -a "$TAG" -m "SnapMark $TAG stable release" "$COMMIT"
git -C "$WORK" push origin "refs/tags/$TAG:refs/tags/$TAG"
find_run "$TAG" "$COMMIT"

echo '===== Verify DEB and AppImage were both released ====='
mapfile -t assets < <(gh release view "$TAG" -R "$REPO" --json assets --jq '.assets[].name')
printf 'Assets:\n%s\n' "${assets[*]}"
for required in 'SnapMark-1.1.1-x86_64.AppImage' \
  'snapmark_1.1.1-1_amd64.deb' \
  'SnapMark-1.1.1-Full-Source.zip' 'SHA256SUMS.txt'; do
  printf '%s\n' "${assets[@]}" | grep -Fxq -- "$required" || {
    echo "Missing release asset $required" >&2; exit 1;
  }
done
[[ "$(gh release view "$TAG" -R "$REPO" --json isPrerelease --jq .isPrerelease)" == false ]] || {
  echo 'Expected a stable release; check release metadata.' >&2; exit 1;
}
echo "Release published: https://github.com/$REPO/releases/tag/$TAG"
echo "Local backup: $BACKUP"
echo "Working checkout: $WORK"
echo "Log: $LOG"
echo 'Previous tags and releases were not modified.'
