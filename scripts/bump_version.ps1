param(
    [ValidateSet("major", "minor", "patch")]
    [string]$Part = "patch",
    [string]$Version,
    [switch]$UpdateDependencyFloors,
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$releaseArgs = @("bump", $Part)
if ($Version) { $releaseArgs += @("--version", $Version) }
if ($UpdateDependencyFloors) { $releaseArgs += "--update-dependency-floors" }
if ($DryRun) { $releaseArgs += "--dry-run" }
& uv run --no-project (Join-Path $PSScriptRoot "release.py") @releaseArgs
if ($LASTEXITCODE -ne 0) { throw "Release command failed (exit code $LASTEXITCODE)" }
