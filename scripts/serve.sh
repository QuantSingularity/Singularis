#!/usr/bin/env bash
# Live lineage dashboard for an experiment, on localhost only.
# Usage: scripts/serve.sh [root] [port]
set -euo pipefail
cd "$(dirname "$0")/.."

singularis serve --root "${1:-runs/exp1}" --port "${2:-8765}"
