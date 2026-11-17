param(
    [string]$Target = "backend/tests"
)

. (Join-Path $PSScriptRoot "_common.ps1")
Import-DotEnv

$env:PYTHONPATH = Join-Path $script:RepoRoot "backend"
Push-Location $script:RepoRoot
try {
    Write-Host "[AegisOps] Running Ruff lint..."
    & "$script:VenvScripts\ruff.exe" check --config backend/pyproject.toml backend
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "[AegisOps] Running Mypy typecheck..."
    & "$script:VenvScripts\mypy.exe" --config-file backend/pyproject.toml backend/app
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "[AegisOps] Running Pytest ($Target)..."
    & "$script:VenvScripts\pytest.exe" -c backend/pyproject.toml $Target -v
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "[AegisOps] Building Frontend..."
    npm --prefix frontend run build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}
