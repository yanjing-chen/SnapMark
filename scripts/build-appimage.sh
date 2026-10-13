#!/usr/bin/env bash
# BUILD MACHINE: GitHub Actions Ubuntu 24.04 x86_64, or Ryzen 7 6800H Ubuntu GNOME Wayland.
# Builds only an AppImage; does not install or modify system packages.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ "$(uname -m)" != x86_64 ]]; then
  echo 'This initial AppImage workflow supports x86_64 only.' >&2
  exit 1
fi
python3 -m unittest discover -s tests -v
python3 -m compileall -q snapmark
python3 scripts/assemble-appdir.py
mkdir -p "$ROOT/dist" "$ROOT/build/tools"
TOOL="$ROOT/build/tools/appimagetool-x86_64.AppImage"
if [[ ! -s "$TOOL" ]]; then
  curl -fL --retry 3 \
    'https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage' \
    -o "$TOOL"
fi
chmod +x "$TOOL"
ARCH=x86_64 VERSION=0.3.0 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" \
  "$ROOT/build/SnapMark.AppDir" "$ROOT/dist/SnapMark-0.3.0-x86_64.AppImage"
chmod +x "$ROOT/dist/SnapMark-0.3.0-x86_64.AppImage"
echo "Created: $ROOT/dist/SnapMark-0.3.0-x86_64.AppImage"
