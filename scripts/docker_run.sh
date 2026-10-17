#!/usr/bin/env bash
# Run any singularis command inside the network-isolated container stack.
# Usage: scripts/docker_run.sh evolve --root runs/exp1 --iterations 5
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p runs
export LOCAL_UID="$(id -u)" LOCAL_GID="$(id -g)"
docker compose -f infrastructure/docker-compose.yml run --rm singularis "$@"
