#!/usr/bin/env bash
# Validate the benchmark, then score the seed genome on the train and held-out splits.
# Usage: scripts/run_baseline.sh [extra singularis eval arguments, e.g. --llm anthropic:<model>]
set -euo pipefail
cd "$(dirname "$0")/.."

singularis validate-suite
singularis eval --split train --out runs/baseline/train "$@"
singularis eval --split heldout --out runs/baseline/heldout "$@"
