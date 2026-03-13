# Load .env file
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match "^\s*([^#][^=]*)=(.*)$") {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            [System.Environment]::SetEnvironmentVariable($name, $value)
        }
    }
}

$ErrorActionPreference = "Stop"

Write-Host "Publishing patera..."
uv publish dist/patera-*

$extensions = @(
    "patera_admin",
    "patera_aiinterface",
    "patera_auth",
    "patera_caching",
    "patera_database",
    "patera_email",
    "patera_frontend",
    "patera_frontendext",
    "patera_statemachine",
    "patera_taskmanager"
)

foreach ($pkg in $extensions) {
    Write-Host "Publishing $pkg..."
    uv publish "dist/$pkg-*"
}

Write-Host "Publish complete."
