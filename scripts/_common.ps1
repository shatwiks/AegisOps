$ErrorActionPreference = "Stop"

$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$script:LocalBin = Join-Path $script:RepoRoot ".local\bin"
$script:VenvDir = Join-Path $script:RepoRoot ".venv"
$script:VenvPython = Join-Path $script:VenvDir "Scripts\python.exe"
$script:VenvScripts = Join-Path $script:VenvDir "Scripts"
$script:EnvFile = Join-Path $script:RepoRoot ".env"
$script:ComposeFile = Join-Path $script:RepoRoot "infra\compose\docker-compose.yml"

if (Test-Path $script:LocalBin) {
    $env:PATH = "$script:LocalBin;$env:PATH"
}
if (Test-Path $script:VenvScripts) {
    $env:PATH = "$script:VenvScripts;$env:PATH"
}

function Import-DotEnv {
    if (-not (Test-Path $script:EnvFile)) { return }
    Get-Content $script:EnvFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $idx = $line.IndexOf("=")
        if ($idx -gt 0) {
            $k = $line.Substring(0, $idx).Trim()
            $v = $line.Substring($idx + 1).Trim()
            [Environment]::SetEnvironmentVariable($k, $v, "Process")
        }
    }
}

function New-RandomHex {
    param([int]$Bytes = 24)
    $buf = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($buf) } finally { $rng.Dispose() }
    return ([System.BitConverter]::ToString($buf) -replace "-", "").ToLowerInvariant()
}

function New-FernetKey {
    $buf = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($buf) } finally { $rng.Dispose() }
    return ([Convert]::ToBase64String($buf)).Replace("+", "-").Replace("/", "_")
}
