. (Join-Path $PSScriptRoot "_common.ps1")

Write-Host "[AegisOps] Running idempotent local setup in $script:RepoRoot"

New-Item -ItemType Directory -Force -Path $script:LocalBin | Out-Null

# 1. Local kind v0.27.0
$kindExe = Join-Path $script:LocalBin "kind.exe"
if (-not (Test-Path $kindExe)) {
    Write-Host "[AegisOps] Downloading kind v0.27.0 into .local/bin/kind.exe ..."
    Invoke-WebRequest -Uri "https://kind.sigs.k8s.io/dl/v0.27.0/kind-windows-amd64" -OutFile $kindExe
}

# 2. Local terraform 1.10.5
$tfExe = Join-Path $script:LocalBin "terraform.exe"
if (-not (Test-Path $tfExe)) {
    Write-Host "[AegisOps] Downloading Terraform 1.10.5 into .local/bin/terraform.exe ..."
    $tfZip = Join-Path $script:LocalBin "terraform.zip"
    Invoke-WebRequest -Uri "https://releases.hashicorp.com/terraform/1.10.5/terraform_1.10.5_windows_amd64.zip" -OutFile $tfZip
    Expand-Archive -Path $tfZip -DestinationPath $script:LocalBin -Force
    Remove-Item -Force $tfZip
}

# 3. Python 3.12 virtualenv via uv
if (-not (Test-Path $script:VenvPython)) {
    Write-Host "[AegisOps] Creating Python 3.12 .venv with uv..."
    uv venv $script:VenvDir --python 3.12
}

Write-Host "[AegisOps] Installing backend Python dependencies into .venv..."
uv pip install --python $script:VenvPython -e "$script:RepoRoot\backend[dev]"
$lockOut = Join-Path $script:RepoRoot "backend\requirements.lock"
uv pip freeze --python $script:VenvPython | Set-Content -Path $lockOut -Encoding utf8

# 4. Frontend npm dependencies
Write-Host "[AegisOps] Installing frontend npm dependencies..."
Push-Location (Join-Path $script:RepoRoot "frontend")
try {
    npm install
} finally {
    Pop-Location
}

# 5. Generate local .env from .env.example if missing
if (-not (Test-Path $script:EnvFile)) {
    Write-Host "[AegisOps] Generating local .env with randomized secrets (never committed)..."
    $template = Get-Content (Join-Path $script:RepoRoot ".env.example") -Raw
    $pgPass = New-RandomHex -Bytes 16
    $content = $template `
        -replace "CHANGE_ME_POSTGRES_PASSWORD", $pgPass `
        -replace "CHANGE_ME_WEBHOOK_HMAC_SECRET", (New-RandomHex -Bytes 24) `
        -replace "CHANGE_ME_WEBHOOK_BEARER_TOKEN", (New-RandomHex -Bytes 24) `
        -replace "CHANGE_ME_FERNET_TOTP_KEY", (New-FernetKey) `
        -replace "CHANGE_ME_SESSION_SECRET", (New-RandomHex -Bytes 32) `
        -replace "CHANGE_ME_KEYCLOAK_ADMIN_PASSWORD", (New-RandomHex -Bytes 16) `
        -replace "CHANGE_ME_KEYCLOAK_DEMO_USER_PASSWORD", (New-RandomHex -Bytes 16) `
        -replace "CHANGE_ME_LANGFUSE_NEXTAUTH_SECRET", (New-RandomHex -Bytes 24) `
        -replace "CHANGE_ME_LANGFUSE_SALT", (New-RandomHex -Bytes 16) `
        -replace "CHANGE_ME_LANGFUSE_HEX_64_KEY", (New-RandomHex -Bytes 32) `
        -replace "CHANGE_ME_DEMO_FAULT_TOKEN", (New-RandomHex -Bytes 20)
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($script:EnvFile, $content, $utf8NoBom)
} else {
    Write-Host "[AegisOps] Existing .env preserved."
}

Write-Host "[AegisOps] Setup completed cleanly."
