. (Join-Path $PSScriptRoot "_common.ps1")
Import-DotEnv

$alembicIni = Join-Path $script:RepoRoot "backend\alembic.ini"
if (-not (Test-Path $alembicIni)) {
    Write-Host "[AegisOps] backend/alembic.ini not present yet (implemented in Phase 1)."
    exit 0
}

Push-Location (Join-Path $script:RepoRoot "backend")
try {
    & $script:VenvPython -m alembic -c $alembicIni upgrade head
} finally {
    Pop-Location
}
