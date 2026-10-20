#!/usr/bin/env bash
# A small real-model run: prints the worst-case cost first, checks the key and the metering path with one tiny
# call, runs the loop under a token cap, and writes runs/live/LIVE_SUMMARY.md.
# Usage: scripts/run_live.sh [extra singularis live arguments]   (add --dry-run to see the cost ceiling only)
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ " $* " != *" --dry-run "* && -z "${ANTHROPIC_API_KEY:-}" && -z "${ANTHROPIC_API_KEY_FILE:-}" ]]; then
  echo "set ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY_FILE) first, or pass --dry-run" >&2
  exit 2
fi
singularis live "$@"
