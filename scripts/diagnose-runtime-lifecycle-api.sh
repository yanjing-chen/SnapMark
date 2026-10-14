#!/usr/bin/env bash
# B2-C1 read-only diagnostic: inspect local Runtime source; no service changes.
set -euo pipefail
printf '%s\n' '===== EXECUTION MACHINE: Ryzen 7 6800H ====='
ROOT="${LOCAL_AI_RUNTIME_ROOT:-$HOME/local-ai-runtime}"
if [[ ! -f "$ROOT/src/local_ai_runtime.py" ]]; then
  echo "Runtime source not found at: $ROOT"
  echo 'Set LOCAL_AI_RUNTIME_ROOT to the local Runtime source checkout.'
  exit 2
fi
printf '\n===== SOURCE REVISION =====\n'
git -C "$ROOT" log -1 --oneline 2>/dev/null || true
printf '\n===== LIFECYCLE, PREFERENCES AND INSTALL SOURCES (READ-ONLY) =====\n'
grep -RnE --include='*.py' --exclude-dir='__pycache__' \
  'idle_unload_seconds|startup_preload|/v1/runtime|backend_preference' \
  "$ROOT/src" | head -n 110 || true
printf '\n===== RELEASE WORKFLOW FILES =====\n'
if [[ -d "$ROOT/.github/workflows" ]]; then
  find "$ROOT/.github/workflows" -maxdepth 1 -type f -printf '%f\n' | sort
else
  echo 'No release workflows found.'
fi
printf '\n===== END: SOURCE READ ONLY; NO API WRITE =====\n'
