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
publish_package "pyjolt"

# Publish extensions
packages=(
  pyjolt_admin
  pyjolt_aiinterface
  pyjolt_auth
  pyjolt_caching
  pyjolt_database
  pyjolt_email
  pyjolt_frontend
  pyjolt_frontendext
  pyjolt_statemachine
  pyjolt_taskmanager
)

for pkg in "${packages[@]}"; do
  publish_package "$pkg"
done

echo "Publish complete."
