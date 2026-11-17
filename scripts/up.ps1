param(
    [switch]$FoundationOnly,
    [switch]$SkipKind,
    [switch]$SkipBuild
)

. (Join-Path $PSScriptRoot "_common.ps1")
Import-DotEnv

# Generate Alertmanager runtime config from template with local secret token (never committed)
$amTmpl = Join-Path $script:RepoRoot "infra\compose\alertmanager\alertmanager.yml.tmpl"
$amGen = Join-Path $script:RepoRoot "infra\compose\alertmanager\alertmanager.generated.yml"
if (Test-Path $amTmpl) {
    $token = $env:AEGISOPS_WEBHOOK_BEARER_TOKEN
    if (-not $token) { throw "AEGISOPS_WEBHOOK_BEARER_TOKEN missing in .env" }
    $amBody = (Get-Content $amTmpl -Raw) -replace "__AEGISOPS_WEBHOOK_BEARER_TOKEN__", $token
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($amGen, $amBody, $utf8NoBom)
}

# Generate Keycloak realm import JSON with local demo user password (never committed)
$kcTmpl = Join-Path $script:RepoRoot "infra\compose\keycloak\realm-aegisops.json.tmpl"
$kcGen = Join-Path $script:RepoRoot "infra\compose\keycloak\realm-aegisops.generated.json"
if (Test-Path $kcTmpl) {
    $demoPw = $env:KEYCLOAK_DEMO_USER_PASSWORD
    if (-not $demoPw) { throw "KEYCLOAK_DEMO_USER_PASSWORD missing in .env" }
    $kcBody = (Get-Content $kcTmpl -Raw) -replace "__AEGISOPS_DEMO_USER_PASSWORD__", $demoPw
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($kcGen, $kcBody, $utf8NoBom)
}

Write-Host "[AegisOps] Starting control-plane backing containers via Docker Compose..."
if ($FoundationOnly) {
    docker compose -f $script:ComposeFile --env-file $script:EnvFile up -d postgres redis
} else {
    docker compose -f $script:ComposeFile --env-file $script:EnvFile --profile obs --profile auth --profile langfuse up -d
}

Write-Host "[AegisOps] Waiting for PostgreSQL and Redis healthchecks..."
$deadline = (Get-Date).AddSeconds(60)
do {
    $pg = docker inspect -f "{{.State.Health.Status}}" aegisops-postgres 2>$null
    $rd = docker inspect -f "{{.State.Health.Status}}" aegisops-redis 2>$null
    if ($pg -eq "healthy" -and $rd -eq "healthy") { break }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)

if ($pg -ne "healthy" -or $rd -ne "healthy") {
    throw "Backing services failed to become healthy (postgres=$pg, redis=$rd)"
}
Write-Host "[AegisOps] Postgres & Redis are healthy."

if ($FoundationOnly) { exit 0 }

if (-not $SkipKind) {
    $oldErr = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $clusters = (kind get clusters 2>&1) | ForEach-Object { $_.ToString() }
    $ErrorActionPreference = $oldErr
    if ($clusters -notcontains "aegisops-local") {
        Write-Host "[AegisOps] Creating kind cluster 'aegisops-local'..."
        kind create cluster --name aegisops-local --config (Join-Path $script:RepoRoot "infra\k8s\kind-config.yaml")
    } else {
        Write-Host "[AegisOps] kind cluster 'aegisops-local' already exists."
    }

    Write-Host "[AegisOps] Applying Terraform Kubernetes resources (namespaces, RBAC, quotas)..."
    $tfDir = Join-Path $script:RepoRoot "infra\terraform"
    Push-Location $tfDir
    try {
        terraform init -input=false | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "terraform init failed" }
        terraform apply -auto-approve -input=false
        if ($LASTEXITCODE -ne 0) { throw "terraform apply failed" }
    } finally {
        Pop-Location
    }

    if (-not $SkipBuild) {
        Write-Host "[AegisOps] Building synthetic healthcare service images..."
        $svcCtx = Join-Path $script:RepoRoot "services"
        docker build -f "$svcCtx\eligibility-api\Dockerfile" -t aegisops/eligibility-api:v1.0.0-good $svcCtx
        if ($LASTEXITCODE -ne 0) { throw "docker build eligibility-api good failed" }
        docker build -f "$svcCtx\eligibility-api\Dockerfile" --build-arg RELEASE_VERSION=v1.9.0-broken --build-arg BROKEN_CANARY=true -t aegisops/eligibility-api:v1.9.0-broken $svcCtx
        if ($LASTEXITCODE -ne 0) { throw "docker build eligibility-api broken failed" }
        docker build -f "$svcCtx\claims-processor\Dockerfile" -t aegisops/claims-processor:v1.0.0-good $svcCtx
        if ($LASTEXITCODE -ne 0) { throw "docker build claims-processor failed" }
        docker build -f "$svcCtx\provider-directory\Dockerfile" -t aegisops/provider-directory:v1.0.0-good $svcCtx
        if ($LASTEXITCODE -ne 0) { throw "docker build provider-directory failed" }

        Write-Host "[AegisOps] Loading service images into kind-aegisops-local..."
        kind load docker-image aegisops/eligibility-api:v1.0.0-good --name aegisops-local
        kind load docker-image aegisops/eligibility-api:v1.9.0-broken --name aegisops-local
        kind load docker-image aegisops/claims-processor:v1.0.0-good --name aegisops-local
        kind load docker-image aegisops/provider-directory:v1.0.0-good --name aegisops-local
    }

    Write-Host "[AegisOps] Creating demo fault-injection secret & deploying workloads..."
    $faultTok = $env:DEMO_INTERNAL_FAULT_TOKEN
    kubectl --context kind-aegisops-local -n aegisops-healthcare create secret generic aegisops-demo-fault-secret --from-literal=token="$faultTok" --dry-run=client -o yaml | kubectl --context kind-aegisops-local apply -f -
    if ($LASTEXITCODE -ne 0) { throw "kubectl secret creation failed" }

    Push-Location $script:RepoRoot
    try {
        kubectl --context kind-aegisops-local apply -f infra/k8s/workloads
        if ($LASTEXITCODE -ne 0) { throw "kubectl apply workloads failed" }
    } finally {
        Pop-Location
    }

    Write-Host "[AegisOps] Waiting for demo workloads to roll out cleanly..."
    foreach ($dep in @("postgres-claims-db", "redis-session-cache", "eligibility-api", "claims-processor", "provider-directory")) {
        kubectl --context kind-aegisops-local -n aegisops-healthcare rollout status "deployment/$dep" --timeout=120s
        if ($LASTEXITCODE -ne 0) { throw "rollout timeout for $dep" }
    }
    kubectl --context kind-aegisops-local -n aegisops-system rollout status deployment/kube-state-metrics --timeout=120s
    if ($LASTEXITCODE -ne 0) { throw "rollout timeout for kube-state-metrics" }
}

Write-Host "[AegisOps] Infrastructure & workloads are ready."
