#!/usr/bin/env bash
set -euo pipefail

# Load credentials
if [[ -f ".env.pypi" ]]; then
  set -a
  source .env.pypi
  set +a
else
  echo "Error: .env.pypi file not found."
  exit 1
fi

: "${UV_PUBLISH_USERNAME:?UV_PUBLISH_USERNAME is not set}"
: "${UV_PUBLISH_PASSWORD:?UV_PUBLISH_PASSWORD is not set}"

publish_package() {
  local prefix="$1"

  shopt -s nullglob
  local files=(dist/"$prefix"-[0-9]*)
  shopt -u nullglob

  if [[ ${#files[@]} -eq 0 ]]; then
    echo "Error: No built files found for $prefix in dist/ (run scripts/build_all.sh)"
    exit 1
  fi

  echo "Publishing $prefix..."
  # --check-url skips files PyPI already has, so a failed run can be repeated.
  uv publish --check-url https://pypi.org/simple/ "${files[@]}"
}

# Dependencies first: every extension needs the core, admin needs auth and
# migrate needs database, so no package is ever uploaded before what it needs.
packages=(
  patera
  patera_database
  patera_auth
  patera_caching
  patera_email
  patera_taskmanager
  patera_apiinterface
  patera_migrate
  patera_admin
  patera_aiinterface
  patera_desktop
)

for pkg in "${packages[@]}"; do
  publish_package "$pkg"
done

echo "Publish complete."
