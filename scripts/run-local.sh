#!/usr/bin/env bash
# MACHINE: Ryzen 7 6800H · Ubuntu GNOME Wayland
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
exec /usr/bin/python3 -m snapmark.app "$@"
