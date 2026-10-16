#!/usr/bin/env bash
# Validate configuration with test values only; this does not start services.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."

# Keep PATH/HOME for Docker CLI plugin discovery, but discard inherited Compose
# settings and application secrets. Explicit files bypass .env and overrides.
# Angle-bracket placeholders are non-secret fixtures recognized by Gitleaks.
env -i PATH="$PATH" HOME="$HOME" \
  CITYFLOW_DATA_DIR=./.local/compose-check \
  RUSTFS_IMAGE=rustfs/rustfs:latest \
  RUSTFS_BIND_IP=127.0.0.1 \
  RUSTFS_S3_PORT=9000 \
  RUSTFS_CONSOLE_PORT=9001 \
  RUSTFS_ACCESS_KEY='<compose-check-access-key>' \
  RUSTFS_SECRET_KEY='<compose-check-secret-key>' \
  docker compose --project-name cityflow-compose-check \
    --env-file /dev/null --file compose.yaml --profile '*' config --quiet

echo 'Compose configuration is valid with test values; service startup was not checked.'
