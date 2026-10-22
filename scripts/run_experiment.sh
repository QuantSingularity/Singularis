#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

ROOT="${1:-runs/experiment}"
ITERATIONS="${2:-5}"
TRIALS="${3:-3}"
shift $(( $# > 3 ? 3 : $# ))

singularis validate-suite
singularis experiment --root "$ROOT" --iterations "$ITERATIONS" --trials "$TRIALS" "$@"
for arm in "$ROOT"/*/; do
  [ -f "${arm}archive.db" ] && singularis verify --root "$arm"
done
