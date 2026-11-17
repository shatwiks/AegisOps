. (Join-Path $PSScriptRoot "_common.ps1")
Import-DotEnv

$failures = 0

function Check-Item {
    param([string]$Label, [scriptblock]$Probe)
    try {
        $msg = & $Probe
        Write-Host ("[OK]   {0,-28} {1}" -f $Label, $msg)
    } catch {
        Write-Host ("[FAIL] {0,-28} {1}" -f $Label, $_.Exception.Message) -ForegroundColor Red
        $script:failures++
    }
}

Write-Host "=== AegisOps Environment Doctor ==="

Check-Item "Python .venv (3.12)" {
    if (-not (Test-Path $script:VenvPython)) { throw "Missing .venv. Run .\scripts\setup.ps1" }
    $ver = (& $script:VenvPython --version) 2>&1
    if ($ver -notmatch "3\.12\.") { throw "Expected Python 3.12, got $ver" }
    return $ver
}

Check-Item "Node / npm" {
    $nv = (node --version).Trim()
    $mv = (npm --version).Trim()
    return "$nv / npm $mv"
}

Check-Item "Docker Desktop" {
    $info = (docker info --format "{{.ServerVersion}} ({{.OperatingSystem}})") 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Docker daemon unreachable" }
    return $info
}

Check-Item "kubectl" {
    $kv = ((kubectl version --client) | Select-Object -First 1) 2>&1
    if ($LASTEXITCODE -ne 0) { throw "kubectl missing or failed" }
    return $kv
}

Check-Item "kind (.local/bin)" {
    $kv = (kind --version) 2>&1
    if ($LASTEXITCODE -ne 0) { throw "kind missing; run .\scripts\setup.ps1" }
    return $kv
}

Check-Item "terraform (.local/bin)" {
    $tv = ((terraform --version) | Select-Object -First 1) 2>&1
    if ($LASTEXITCODE -ne 0) { throw "terraform missing; run .\scripts\setup.ps1" }
    return $tv
}

Check-Item "k6" {
    return ((k6 version) | Select-Object -First 1)
}

Check-Item "Ollama models cached" {
    $manifestRoot = Join-Path $env:USERPROFILE ".ollama\models\manifests\registry.ollama.ai\library"
    $nomic = Test-Path (Join-Path $manifestRoot "nomic-embed-text\latest")
    $llama = Test-Path (Join-Path $manifestRoot "llama3.2\3b")
    if (-not ($nomic -and $llama)) {
        throw "Required cached models nomic-embed-text:latest or llama3.2:3b missing"
    }
    return "nomic-embed-text:latest & llama3.2:3b cached"
}

Check-Item "Validated .env settings" {
    if (-not (Test-Path $script:EnvFile)) { throw "Missing .env; run .\scripts\setup.ps1" }
    $env:PYTHONPATH = Join-Path $script:RepoRoot "backend"
    $out = & $script:VenvPython -c "from app.config import get_settings; s = get_settings(); print(f'env={s.aegisops_env}, ctx={s.aegisops_k8s_context}, dim={s.aegisops_embedding_dimensions}')" 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($out -join " ") }
    return $out
}

Check-Item "Compose YAML validity" {
    docker compose -f $script:ComposeFile config --quiet
    if ($LASTEXITCODE -ne 0) { throw "Compose config validation failed" }
    return "infra/compose/docker-compose.yml valid"
}

$ports = @(53000, 55173, 55317, 55318, 55432, 56379, 58000, 58080, 58081, 58082, 58083, 58084, 58889, 59090, 59093)
Write-Host ""
Write-Host "=== Port Status Summary ==="
$activeListeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | ForEach-Object { $_.Port }
foreach ($p in $ports) {
    $inUse = $activeListeners -contains $p
    $state = if ($inUse) { "IN_USE" } else { "FREE" }
    Write-Host ("  Port {0,-6} : {1}" -f $p, $state)
}

if ($failures -gt 0) {
    Write-Host "`nDoctor failed with $failures error(s)." -ForegroundColor Red
    exit 1
}
Write-Host "`nDoctor checks passed." -ForegroundColor Green
