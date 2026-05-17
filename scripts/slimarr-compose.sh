#!/usr/bin/env bash
set -euo pipefail

COMPOSE_URL="https://raw.githubusercontent.com/theantipopau/slimarr/main/docker-compose.yml"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker command not found." >&2
  exit 1
fi

if [ "$#" -eq 0 ]; then
  set -- up -d
fi

echo "Using compose template: ${COMPOSE_URL}"
curl -fsSL "${COMPOSE_URL}" | docker compose -f - "$@"