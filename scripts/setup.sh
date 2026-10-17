#!/usr/bin/env bash
# Create a virtual environment and install Singularis with the Anthropic client and dev tools.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[anthropic,dev]"
echo "Setup complete. Activate with: source .venv/bin/activate"
