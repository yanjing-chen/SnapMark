#!/usr/bin/env bash
# MACHINE: Ryzen 7 6800H · Ubuntu GNOME Wayland
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -x "$HOME/.local/bin/snapmark" ]]; then
  echo 'Install SnapMark first: bash scripts/install-local.sh' >&2
  exit 1
fi
mkdir -p "$HOME/.config/autostart"
cp "$ROOT/assets/io.github.yanjingchen.SnapMark-watcher.desktop" \
 "$HOME/.config/autostart/io.github.yanjingchen.SnapMark-watcher.desktop"
"$HOME/.local/bin/snapmark" --login-start &
echo 'Screenshot monitoring is enabled for this GNOME session and future logins.'
