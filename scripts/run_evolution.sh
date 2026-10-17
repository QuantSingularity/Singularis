#!/usr/bin/env bash
# Run the recursive self-improvement loop (resumable) and write the report for the frontend.
# Usage: scripts/run_evolution.sh [root] [iterations] [extra singularis evolve arguments]
set -euo pipefail
cd "$(dirname "$0")/.."

ROOT="${1:-runs/exp1}"
ITERATIONS="${2:-5}"
shift $(( $# > 2 ? 2 : $# ))

singularis evolve --root "$ROOT" --iterations "$ITERATIONS" "$@"
singularis report --root "$ROOT"
