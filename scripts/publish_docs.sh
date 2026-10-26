#!/usr/bin/env bash
# Publish the documentation version of the checked-out release (see DOCS_PUBLISHING.md).
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec uv run --no-project "$script_dir/docs.py" deploy "$@"
