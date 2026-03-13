$ErrorActionPreference = "Stop"

Write-Host "Building core package: patera"
uv build --package patera

$packagesDir = "packages"

Get-ChildItem $packagesDir -Directory | ForEach-Object {
    $pkg = $_.Name
    Write-Host "Building package: $pkg"
    uv build --package $pkg
}

Write-Host "All packages built successfully."
