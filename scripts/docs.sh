#!/usr/bin/env bash
# Documentation helper: serve | build | list | serve-versions | deploy | delete
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec uv run --no-project "$script_dir/docs.py" "$@"
