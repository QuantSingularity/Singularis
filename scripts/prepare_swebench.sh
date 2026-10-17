#!/usr/bin/env bash
# Turn a SWE-bench style dataset file into task directories and check them.
# Usage: scripts/prepare_swebench.sh DATASET.jsonl [out_dir] [python_with_repo_dependencies] [extra prepare arguments]
# Needs network access to clone the repositories (run this on the host, not inside the isolated container).
set -euo pipefail
cd "$(dirname "$0")/.."

DATASET="${1:?usage: prepare_swebench.sh DATASET.jsonl [out_dir] [python]}"
OUT="${2:-tasks/swebench}"
PYTHON="${3:-}"
shift $(( $# > 3 ? 3 : $# ))

singularis swebench prepare --dataset "$DATASET" --out "$OUT" ${PYTHON:+--python "$PYTHON"} "$@"
singularis validate-suite --tasks-dir "$OUT"
