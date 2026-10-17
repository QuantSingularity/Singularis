#!/usr/bin/env bash
# Real browser check of the live dashboard. Installs Playwright and Chromium on first use.
set -euo pipefail
cd "$(dirname "$0")/.."

python -m pip install --quiet playwright
python -m playwright install chromium
python frontend/test/browser_live.py
