$ErrorActionPreference = "Stop"

# Start from an empty dist/ so only this version's files get published.
if (Test-Path "dist") { Remove-Item "dist" -Recurse -Force }
New-Item -ItemType Directory -Path "dist" | Out-Null

function Invoke-Checked([string]$Description, [scriptblock]$Command) {
    Write-Host $Description
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Description failed (exit code $LASTEXITCODE)" }
}

Invoke-Checked "Building core package: patera" { uv build --package patera --out-dir dist }

Get-ChildItem "packages" -Directory | ForEach-Object {
    $pkg = $_.Name
    Invoke-Checked "Building package: $pkg" { uv build --package $pkg --out-dir dist }
}

$files = Get-ChildItem "dist" -File | ForEach-Object { $_.FullName }
Invoke-Checked "Checking package metadata..." { uvx twine check --strict @files }

Write-Host "All packages built and checked."
