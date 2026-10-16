#!/usr/bin/env bash
# Install the same verified release locally and in the unprivileged CI container.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: bash infra/scripts/install-gitleaks.sh DESTINATION" >&2
  exit 2
fi

version=8.30.1
case "$(uname -s)/$(uname -m)" in
  Linux/x86_64)
    platform=linux_x64
    checksum=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
    ;;
  Linux/aarch64|Linux/arm64)
    platform=linux_arm64
    checksum=e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080
    ;;
  Darwin/arm64)
    platform=darwin_arm64
    checksum=b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5
    ;;
  Darwin/x86_64)
    platform=darwin_x64
    checksum=dfe101a4db2255fc85120ac7f3d25e4342c3c20cf749f2c20a18081af1952709
    ;;
  *)
    echo "Unsupported platform: $(uname -s)/$(uname -m)" >&2
    exit 2
    ;;
esac

destination=$1
download_dir=$(mktemp -d)
trap 'rm -rf "$download_dir"' EXIT
archive="gitleaks_${version}_${platform}.tar.gz"
curl --fail --silent --show-error --location --retry 3 \
  --connect-timeout 15 --max-time 120 \
  "https://github.com/gitleaks/gitleaks/releases/download/v${version}/${archive}" \
  --output "$download_dir/$archive"

if command -v sha256sum >/dev/null 2>&1; then
  actual_checksum=$(sha256sum "$download_dir/$archive")
else
  actual_checksum=$(shasum -a 256 "$download_dir/$archive")
fi
if [[ ${actual_checksum%% *} != "$checksum" ]]; then
  echo "Gitleaks archive checksum mismatch; refusing to install." >&2
  exit 1
fi

tar -xzf "$download_dir/$archive" -C "$download_dir" gitleaks
mkdir -p "$destination"
install -m 0755 "$download_dir/gitleaks" "$destination/gitleaks"
"$destination/gitleaks" version
