param([switch]$DryRun)
$ErrorActionPreference = "Stop"
$releaseArgs = @("build")
if ($DryRun) { $releaseArgs += "--dry-run" }
& uv run --no-project (Join-Path $PSScriptRoot "release.py") @releaseArgs @args
if ($LASTEXITCODE -ne 0) { throw "Release command failed (exit code $LASTEXITCODE)" }
