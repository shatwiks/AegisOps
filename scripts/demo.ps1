param(
    [string]$Scenario = "all"
)

. (Join-Path $PSScriptRoot "_common.ps1")
Import-DotEnv

$chaosRunner = Join-Path $script:RepoRoot "chaos\run_scenario.py"
if (-not (Test-Path $chaosRunner)) {
    throw "chaos/run_scenario.py is implemented in Phase 5."
}
$env:PYTHONPATH = Join-Path $script:RepoRoot "backend"
& $script:VenvPython $chaosRunner --scenario $Scenario
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
