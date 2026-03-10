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

Write-Host "Publishing pyjolt..."
uv publish dist/pyjolt-*

$extensions = @(
    "pyjolt_admin",
    "pyjolt_aiinterface",
    "pyjolt_auth",
    "pyjolt_caching",
    "pyjolt_database",
    "pyjolt_email",
    "pyjolt_frontend",
    "pyjolt_frontendext",
    "pyjolt_statemachine",
    "pyjolt_taskmanager"
)

foreach ($pkg in $extensions) {
    Write-Host "Publishing $pkg..."
    uv publish "dist/$pkg-*"
}

Write-Host "Publish complete."
