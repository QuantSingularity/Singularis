#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p runs
export LOCAL_UID="$(id -u)" LOCAL_GID="$(id -g)"
COMPOSE=(docker compose -f infrastructure/docker-compose.yml)

"${COMPOSE[@]}" build
"${COMPOSE[@]}" run --rm singularis isolation-check --runs /app/runs
"${COMPOSE[@]}" run --rm singularis validate-suite
"${COMPOSE[@]}" run --rm singularis eval --llm scripted:/app/smoke/solve.json --only fizzbuzz --out runs/docker_smoke
"${COMPOSE[@]}" down
echo "Docker stack verified"
