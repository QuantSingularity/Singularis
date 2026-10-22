#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

ROOT="${1:-runs/exp1}"
ITERATIONS="${2:-5}"
shift $(( $# > 2 ? 2 : $# ))

singularis evolve --root "$ROOT" --iterations "$ITERATIONS" "$@"
singularis report --root "$ROOT"
