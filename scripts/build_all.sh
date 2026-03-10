#!/usr/bin/env bash
set -e

echo "Building core package..."
uv build --package pyjolt

for dir in packages/*; do
  pkg=$(basename "$dir")
  echo "Building $pkg..."
  uv build --package "$pkg"
done

echo "All packages built."
