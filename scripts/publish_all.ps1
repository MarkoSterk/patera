$ErrorActionPreference = "Stop"

# Load credentials
if (-not (Test-Path ".env.pypi")) { throw "Error: .env.pypi file not found." }
Get-Content ".env.pypi" | ForEach-Object {
    if ($_ -match "^\s*([^#][^=]*)=(.*)$") {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim())
    }
}
if (-not $env:UV_PUBLISH_USERNAME -or -not $env:UV_PUBLISH_PASSWORD) {
    throw "UV_PUBLISH_USERNAME and UV_PUBLISH_PASSWORD must be set in .env.pypi"
}

# Dependencies first: every extension needs the core, admin needs auth and
# migrate needs database, so no package is ever uploaded before what it needs.
$packages = @(
    "patera",
    "patera_database",
    "patera_auth",
    "patera_caching",
    "patera_email",
    "patera_taskmanager",
    "patera_apiinterface",
    "patera_migrate",
    "patera_admin",
    "patera_aiinterface",
    "patera_desktop"
)

foreach ($pkg in $packages) {
    $files = Get-ChildItem "dist" -File | Where-Object { $_.Name -match "^$pkg-[0-9]" } | ForEach-Object { $_.FullName }
    if (-not $files) { throw "No built files found for $pkg in dist/ (run scripts/build_all.ps1)" }
    Write-Host "Publishing $pkg..."
    # --check-url skips files PyPI already has, so a failed run can be repeated.
    uv publish --check-url https://pypi.org/simple/ @files
    if ($LASTEXITCODE -ne 0) { throw "Publishing $pkg failed (exit code $LASTEXITCODE)" }
}

Write-Host "Publish complete."
