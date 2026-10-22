#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

singularis report --root "${1:-runs/exp1}"
