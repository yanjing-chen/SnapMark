#!/usr/bin/env bash
# MACHINE: Ryzen 7 6800H · Ubuntu GNOME Wayland
set -euo pipefail
rm -f "$HOME/.config/autostart/io.github.yanjingchen.SnapMark-watcher.desktop"
echo 'Autostart disabled for future logins. Existing watcher may remain until logout.'
