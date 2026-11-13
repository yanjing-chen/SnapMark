#!/usr/bin/env bash
# Build native Ubuntu/Debian package from the SnapMark complete source tree.
# No Ollama model, Local Runtime, user configuration or third-party GTK copies.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo 'Please install dpkg-dev: sudo apt install -y dpkg-dev' >&2
  exit 1
fi
PYTHON="${SNAPMARK_PYTHON:-/usr/bin/python3}"
[ -x "$PYTHON" ] || { echo "Missing host Python: $PYTHON" >&2; exit 1; }
VERSION="$($PYTHON -c 'from snapmark import __version__; print(__version__)')"
case "$VERSION" in
  *-rc[0-9]*) DEB_VERSION="${VERSION/-rc/~rc}-1" ;;
  *) DEB_VERSION="$VERSION-1" ;;
esac
ARCH="$(dpkg --print-architecture)"
if [ "$ARCH" != amd64 ]; then
  echo "This release currently targets amd64; got $ARCH" >&2
  exit 1
fi

"$PYTHON" -m compileall -q snapmark
STAGE="$(mktemp -d -t snapmark-deb.XXXXXXXX)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/DEBIAN" "$STAGE/usr/bin" "$STAGE/usr/share/snapmark" \
  "$STAGE/usr/share/applications" "$STAGE/usr/share/doc/snapmark"
"$PYTHON" - "$ROOT" "$STAGE" <<'PY'
from pathlib import Path
import shutil, sys
root, stage = map(Path, sys.argv[1:])
shutil.copytree(root/'snapmark', stage/'usr/share/snapmark/snapmark',
                ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
# Tray's source-relative fallback resolves this asset when installed in /usr/share.
asset_dir=stage/'usr/share/snapmark/assets'; asset_dir.mkdir(parents=True)
shutil.copy2(root/'assets/io.github.yanjingchen.SnapMark-32.png', asset_dir)
for size in (32,64,128,256):
    dst=stage/f'usr/share/icons/hicolor/{size}x{size}/apps'
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root/f'assets/io.github.yanjingchen.SnapMark-{size}.png',
                 dst/'io.github.yanjingchen.SnapMark.png')
shutil.copy2(root/'LICENSE', stage/'usr/share/doc/snapmark/LICENSE')
PY
cat > "$STAGE/usr/bin/snapmark" <<'LAUNCHER'
#!/usr/bin/env bash
# /usr/bin/snapmark uses one coherent set of system GTK4/libadwaita libraries.
set -euo pipefail
export PYTHONPATH="/usr/share/snapmark"
export PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
exec /usr/bin/python3 -m snapmark.app "$@"
LAUNCHER
chmod 0755 "$STAGE/usr/bin/snapmark"
# Fully qualified Exec avoids older ~/.local/bin/snapmark shadowing this package.
sed 's|^Exec=snapmark$|Exec=/usr/bin/snapmark|' \
  assets/io.github.yanjingchen.SnapMark.desktop > \
  "$STAGE/usr/share/applications/io.github.yanjingchen.SnapMark.desktop"
cat > "$STAGE/DEBIAN/control" <<CONTROL
Package: snapmark
Version: $DEB_VERSION
Section: graphics
Priority: optional
Architecture: $ARCH
Maintainer: SnapMark Contributors <noreply@github.com>
Depends: python3 (>= 3.10), python3-gi, python3-gi-cairo, python3-cairo, gir1.2-gtk-4.0, gir1.2-adw-1, gir1.2-gdkpixbuf-2.0, gir1.2-pango-1.0, libgtk-4-1, libadwaita-1-0
Homepage: https://github.com/yanjing-chen/SnapMark
Description: Native GNOME screenshot editor with optional Ollama OCR
 SnapMark is a GTK4/libadwaita screenshot editor with markup, history and
 optional local OCR through an independently installed Ollama service.
 No OCR models, AI runtime or system GPU drivers are installed by this package.
CONTROL
chmod 0644 "$STAGE/DEBIAN/control"
# Worktrees on shared folders can inherit setgid (2755), rejected by dpkg-deb.
find "$STAGE" -type d -exec chmod 0755 {} +
mkdir -p "$ROOT/dist"
OUT="$ROOT/dist/snapmark_${DEB_VERSION}_${ARCH}.deb"
dpkg-deb --build --root-owner-group "$STAGE" "$OUT"
dpkg-deb --info "$OUT" | tee "$ROOT/dist/deb-metadata.txt"
dpkg-deb --contents "$OUT" > "$ROOT/dist/deb-file-list.txt"
test -s "$OUT"
echo "Created: $OUT"
