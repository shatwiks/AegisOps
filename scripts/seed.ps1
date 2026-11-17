param(
    [switch]$CmdbOnly
)

. (Join-Path $PSScriptRoot "_common.ps1")
Import-DotEnv

$env:PYTHONPATH = Join-Path $script:RepoRoot "backend"
$cmdbScript = Join-Path $script:RepoRoot "backend\app\seed\cmdb_seed.py"
$runbookScript = Join-Path $script:RepoRoot "backend\app\seed\runbook_seed.py"

if (Test-Path $cmdbScript) {
    Write-Host "[AegisOps] Seeding CMDB topology..."
    & $script:VenvPython -m app.seed.cmdb_seed
} else {
    Write-Host "[AegisOps] CMDB seed module not created yet (Phase 1)."
}

if (-not $CmdbOnly) {
    if (Test-Path $runbookScript) {
        Write-Host "[AegisOps] Seeding SRE runbooks and embeddings..."
        & $script:VenvPython -m app.seed.runbook_seed
    } else {
        Write-Host "[AegisOps] Runbook seed module not created yet (Phase 2)."
    }
}
