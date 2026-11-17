. (Join-Path $PSScriptRoot "_common.ps1")
Import-DotEnv

Write-Host "[AegisOps] Stopping Compose containers (non-destructive; volumes preserved)..."
docker compose -f $script:ComposeFile down --remove-orphans
Write-Host "[AegisOps] Shutdown complete."
