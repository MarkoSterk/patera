param([switch]$DryRun)
$ErrorActionPreference = "Stop"
$releaseArgs = @("publish")
if ($DryRun) { $releaseArgs += "--dry-run" }
& uv run --no-project (Join-Path $PSScriptRoot "release.py") @releaseArgs
if ($LASTEXITCODE -ne 0) { throw "Release command failed (exit code $LASTEXITCODE)" }
