#!/usr/bin/env bash
# Deploy a reviewed main branch to CityFlow VM 110.
# Runs on VM 110 as alex (must have Docker access).
set -euo pipefail
cd /home/alex/projects/cityflow

# Keep the local runtime .env and /srv/cityflow data outside Git.
git fetch --prune origin main
git switch main
git merge --ff-only origin/main

if [[ ! -f .env ]]; then
  echo 'Missing local .env on VM 110' >&2
  exit 1
fi

docker compose config --quiet
# Initial stage: only reconcile the RustFS service. Later deploy
# dashboard/dagster after these services have been added to compose.yaml.
docker compose up -d --no-deps rustfs
docker compose ps rustfs
printf 'CityFlow deploy complete: %s\n' "$(git rev-parse --short HEAD)"
