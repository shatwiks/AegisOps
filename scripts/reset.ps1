param(
    [switch]$Force
)

. (Join-Path $PSScriptRoot "_common.ps1")
Import-DotEnv

if (-not $Force) {
    throw "Destructive reset requires -Force. This removes ONLY AegisOps Compose volumes and kind cluster 'aegisops-local'."
}

Write-Host "[AegisOps] Destructively resetting AegisOps local Compose volumes and kind cluster..."
docker compose -f $script:ComposeFile down -v --remove-orphans

if (Get-Command kind -ErrorAction SilentlyContinue) {
    $clusters = kind get clusters 2>$null
    if ($clusters -contains "aegisops-local") {
        kind delete cluster --name aegisops-local
    }
}

Write-Host "[AegisOps] AegisOps resources reset."
