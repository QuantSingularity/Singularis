#!/usr/bin/env bash
# Write report.json for an experiment so it can be opened in frontend/index.html.
# Usage: scripts/make_report.sh [root]
set -euo pipefail
cd "$(dirname "$0")/.."

singularis report --root "${1:-runs/exp1}"
