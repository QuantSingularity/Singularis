#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

DATASET="${1:?usage: prepare_swebench.sh DATASET.jsonl [out_dir] [python]}"
OUT="${2:-tasks/swebench}"
PYTHON="${3:-}"
shift $(( $# > 3 ? 3 : $# ))

singularis swebench prepare --dataset "$DATASET" --out "$OUT" ${PYTHON:+--python "$PYTHON"} "$@"
singularis validate-suite --tasks-dir "$OUT"
