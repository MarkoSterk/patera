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

# Only the distributions: uv build also writes a .gitignore into dist/.
$files = Get-ChildItem "dist" -File |
    Where-Object { $_.Name -like "*.whl" -or $_.Name -like "*.tar.gz" } |
    ForEach-Object { $_.FullName }
if (-not $files) { throw "No distributions found in dist/" }
Invoke-Checked "Checking package metadata..." { uvx twine check --strict @files }

Write-Host "All packages built and checked."
