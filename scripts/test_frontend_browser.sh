#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

python -m pip install --quiet playwright
python -m playwright install chromium
python frontend/test/browser_live.py
