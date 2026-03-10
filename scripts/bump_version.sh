#!/usr/bin/env bash
set -euo pipefail

part="${1:-patch}"

if [[ "$part" != "major" && "$part" != "minor" && "$part" != "patch" ]]; then
  echo "Usage: ./bump_all.sh [major|minor|patch]"
  exit 1
fi

echo "Bumping pyjolt ($part)..."
uv version --package pyjolt --bump "$part"

for dir in packages/*; do
  if [[ -f "$dir/pyproject.toml" ]]; then
    pkg="$(basename "$dir")"
    echo "Bumping $pkg ($part)..."
    uv version --package "$pkg" --bump "$part"
  fi
done

echo "Done."
