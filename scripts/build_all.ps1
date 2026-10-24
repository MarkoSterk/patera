$ErrorActionPreference = "Stop"
& uv run --no-project (Join-Path $PSScriptRoot "release.py") build @args
if ($LASTEXITCODE -ne 0) { throw "Release command failed (exit code $LASTEXITCODE)" }
