#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ " $* " != *" --dry-run "* && -z "${ANTHROPIC_API_KEY:-}" && -z "${ANTHROPIC_API_KEY_FILE:-}" ]]; then
  echo "set ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY_FILE) first, or pass --dry-run" >&2
  exit 2
fi
singularis live "$@"
