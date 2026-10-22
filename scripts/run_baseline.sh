#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

singularis validate-suite
singularis eval --split train --out runs/baseline/train "$@"
singularis eval --split heldout --out runs/baseline/heldout "$@"
