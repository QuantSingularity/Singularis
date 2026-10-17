#!/usr/bin/env bash
# Run the full test suite. Extra arguments are passed to pytest.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m pytest "$@"
