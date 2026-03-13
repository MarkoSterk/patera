#!/usr/bin/env bash
set -euo pipefail

# Load .env
if [[ -f ".env" ]]; then
  set -a
  source .env
  set +a
else
  echo "Error: .env file not found."
  exit 1
fi

# Safety checks
: "${UV_PUBLISH_USERNAME:?UV_PUBLISH_USERNAME is not set}"
: "${UV_PUBLISH_PASSWORD:?UV_PUBLISH_PASSWORD is not set}"

publish_package() {
  local prefix="$1"

  shopt -s nullglob
  local files=(dist/"$prefix"-*)
  shopt -u nullglob

  if [[ ${#files[@]} -eq 0 ]]; then
    echo "Error: No built files found for $prefix in dist/"
    exit 1
  fi

  echo "Publishing $prefix..."
  uv publish "${files[@]}"
}

# Publish core first
publish_package "patera"

# Publish extensions
packages=(
  patera_admin
  patera_aiinterface
  patera_auth
  patera_caching
  patera_database
  patera_email
  patera_frontend
  patera_frontendext
  patera_statemachine
  patera_taskmanager
)

for pkg in "${packages[@]}"; do
  publish_package "$pkg"
done

echo "Publish complete."
