#!/usr/bin/env bash
# MACHINE: Ubuntu GNOME / GTK4 (including RTX 5070)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
exec /usr/bin/python3 -m snapmark.app "$@"
