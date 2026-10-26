# Documentation helper: serve | build | list | serve-versions | deploy | delete
$ErrorActionPreference = "Stop"
& uv run --no-project (Join-Path $PSScriptRoot "docs.py") @args
if ($LASTEXITCODE -ne 0) { throw "Docs command failed (exit code $LASTEXITCODE)" }
