#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

singularis serve --root "${1:-runs/exp1}" --port "${2:-8765}"
