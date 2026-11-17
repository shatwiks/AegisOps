param(
    [string]$Service = ""
)

. (Join-Path $PSScriptRoot "_common.ps1")
Import-DotEnv

if ($Service) {
    docker compose -f $script:ComposeFile logs --tail 100 $Service
} else {
    docker compose -f $script:ComposeFile logs --tail 50
}
