#!/usr/bin/env bash
# Compare evolution arms against the unmodified seed with confidence intervals.
# Usage: scripts/run_experiment.sh [root] [iterations] [trials] [extra singularis experiment arguments]
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
