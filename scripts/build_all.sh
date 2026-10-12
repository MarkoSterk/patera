#!/usr/bin/env bash
set -euo pipefail

# Start from an empty dist/ so only this version's files get published.
rm -rf dist
mkdir -p dist

echo "Building core package..."
uv build --package patera --out-dir dist

for dir in packages/*; do
  pkg=$(basename "$dir")
  echo "Building $pkg..."
  uv build --package "$pkg" --out-dir dist
done

echo "Checking package metadata..."
# Only the distributions: uv build also writes a .gitignore into dist/.
uvx twine check --strict dist/*.whl dist/*.tar.gz

echo "All packages built and checked."
