#!/usr/bin/env bash
# MACHINE: Ryzen 7 6800H · Ubuntu GNOME Wayland
# Installs only to this user's ~/.local directory.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="${HOME}/.local"
mkdir -p "$PREFIX/share/snapmark" "$PREFIX/bin" "$PREFIX/share/applications" "$PREFIX/share/icons/hicolor/256x256/apps" "$PREFIX/share/icons/hicolor/32x32/apps"
cp -R "$ROOT/snapmark" "$PREFIX/share/snapmark/"
cp "$ROOT/assets/io.github.yanjingchen.SnapMark.desktop" "$PREFIX/share/applications/"
cp "$ROOT/assets/io.github.yanjingchen.SnapMark-256.png" "$PREFIX/share/icons/hicolor/256x256/apps/io.github.yanjingchen.SnapMark.png"
cp "$ROOT/assets/io.github.yanjingchen.SnapMark-32.png" "$PREFIX/share/icons/hicolor/32x32/apps/io.github.yanjingchen.SnapMark.png"
cat > "$PREFIX/bin/snapmark" <<'LAUNCH'
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="${HOME}/.local/share/snapmark${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m snapmark.app "$@"
LAUNCH
chmod +x "$PREFIX/bin/snapmark"
cat <<'END'
SnapMark installed locally.
Run: ~/.local/bin/snapmark
Enable automatic opening after GNOME screenshots:
    bash scripts/enable-autostart.sh
END
