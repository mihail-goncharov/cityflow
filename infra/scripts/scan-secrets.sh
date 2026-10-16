#!/usr/bin/env bash
# Run from any directory inside the repository; requires gitleaks on PATH.
set -euo pipefail

usage() {
  echo "Usage: bash infra/scripts/scan-secrets.sh {staged|history|changes BASE [HEAD]}" >&2
  exit 2
}

[[ $# -ge 1 ]] || usage
mode=$1
cd "$(git rev-parse --show-toplevel)"
options=(--config .gitleaks.toml --redact=100 --verbose --no-banner --no-color)

if [[ $mode == staged && $# -eq 1 ]]; then
  exec gitleaks git "${options[@]}" --staged .
fi

if [[ $(git rev-parse --is-shallow-repository) == true ]]; then
  echo "Secret scanning requires full Git history: fetch with --unshallow or checkout with fetch-depth: 0." >&2
  exit 2
fi

# Include merge resolutions as well as ordinary commits and renamed files.
log_options="--full-history --diff-merges=first-parent --no-renames"
case "$mode" in
  history)
    [[ $# -eq 1 ]] || usage
    log_options="$log_options --all"
    ;;
  changes)
    [[ $# -ge 2 && $# -le 3 ]] || usage
    base=$2
    head=$(git rev-parse --verify --end-of-options "${3:-HEAD}^{commit}")
    if [[ -z $base || $base =~ ^0+$ ]] || \
       ! base=$(git rev-parse --verify --end-of-options "${base}^{commit}" 2>/dev/null); then
      # New branch or an unavailable pre-force-push commit: never silently skip.
      echo "No available base commit; scanning all fetched history."
      log_options="$log_options --all $head"
    else
      log_options="$log_options $base..$head"
    fi
    ;;
  *) usage ;;
esac

exec gitleaks git "${options[@]}" --log-opts="$log_options" .
