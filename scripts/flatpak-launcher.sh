#!/usr/bin/env bash
# Installed as /app/bin/snapmark inside a sandbox.
set -euo pipefail
export PYTHONPATH="/app/share/snapmark${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m snapmark.app "$@"
