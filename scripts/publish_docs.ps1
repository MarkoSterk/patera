# Publish the documentation version of the checked-out release (see DOCS_PUBLISHING.md).
param(
    [string]$Version,
    [switch]$Dev,
    [string]$Title,
    [switch]$NoLatest,
    [switch]$SetDefault,
    [switch]$NoPush,
    [switch]$AllowUntagged,
    [switch]$AllowDirty,
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$docsArgs = @("deploy")
if ($Version) { $docsArgs += @("--version", $Version) }
if ($Dev) { $docsArgs += "--dev" }
if ($Title) { $docsArgs += @("--title", $Title) }
if ($NoLatest) { $docsArgs += "--no-latest" }
if ($SetDefault) { $docsArgs += "--set-default" }
if ($NoPush) { $docsArgs += "--no-push" }
if ($AllowUntagged) { $docsArgs += "--allow-untagged" }
if ($AllowDirty) { $docsArgs += "--allow-dirty" }
if ($DryRun) { $docsArgs += "--dry-run" }
& uv run --no-project (Join-Path $PSScriptRoot "docs.py") @docsArgs @args
if ($LASTEXITCODE -ne 0) { throw "Docs publish failed (exit code $LASTEXITCODE)" }
