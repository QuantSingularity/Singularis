#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p runs
export LOCAL_UID="$(id -u)" LOCAL_GID="$(id -g)"
docker compose -f infrastructure/docker-compose.yml run --rm singularis "$@"
