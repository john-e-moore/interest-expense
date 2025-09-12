#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   scripts/run.sh [CONFIG] [OUTDIR]
# Defaults:
#   CONFIG = input/macro.yaml
#   OUTDIR = output

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

CONFIG="${1:-$ROOT/input/macro.yaml}"
OUTDIR="${2:-$ROOT/output}"

exec "$PY" "$ROOT/scripts/run_forward.py" \
  --config "$CONFIG" \
  --diagnostics \
  --perf \
  --debug \
  --uat \
  --outdir "$OUTDIR"


