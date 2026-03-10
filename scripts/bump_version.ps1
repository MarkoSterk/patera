param(
    [ValidateSet("major", "minor", "patch")]
    [string]$Part = "patch"
)

$ErrorActionPreference = "Stop"

$packages = @("pyjolt")

Get-ChildItem "packages" -Directory | ForEach-Object {
    if (Test-Path "$($_.FullName)\pyproject.toml") {
        $packages += $_.Name
    }
}

foreach ($pkg in $packages) {
    Write-Host "Bumping $pkg ($Part)..."
    uv version --package $pkg --bump $Part
}

Write-Host "Done."
