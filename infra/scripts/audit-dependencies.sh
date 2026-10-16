#!/usr/bin/env bash
# Audit the locked dependency versions for the current Python and platform.
# Install development tools first with: uv sync --locked --group ci
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
audit_dir=$(mktemp -d)
trap 'rm -rf "$audit_dir"' EXIT

# uv exports the complete transitive dependency graph, including dev/CI tools.
# Exclude the local project; it is not a published third-party dependency.
uv export --locked --all-groups --no-emit-project \
  --output-file "$audit_dir/requirements.txt" > /dev/null

# Requirements are already pinned by uv: audit without resolving/installing again.
uv run --no-sync pip-audit --strict --require-hashes --disable-pip \
  --progress-spinner off --aliases \
  --requirement "$audit_dir/requirements.txt"
