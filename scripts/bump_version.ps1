param(
    [ValidateSet("major", "minor", "patch")]
    [string]$Part = "patch",
    [switch]$UpdateDependencyFloors,
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$releaseArgs = @("bump", $Part)
if ($UpdateDependencyFloors) { $releaseArgs += "--update-dependency-floors" }
if ($DryRun) { $releaseArgs += "--dry-run" }
& uv run --no-project (Join-Path $PSScriptRoot "release.py") @releaseArgs
if ($LASTEXITCODE -ne 0) { throw "Release command failed (exit code $LASTEXITCODE)" }
