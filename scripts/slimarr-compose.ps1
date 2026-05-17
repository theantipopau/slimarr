param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ComposeArgs = @("up", "-d")
)

$ErrorActionPreference = "Stop"

$composeUrl = "https://raw.githubusercontent.com/theantipopau/slimarr/main/docker-compose.yml"

Write-Host "Using compose template: $composeUrl" -ForegroundColor Cyan

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: docker command not found." -ForegroundColor Red
    exit 1
}

$composeContent = (Invoke-WebRequest -UseBasicParsing $composeUrl).Content
if (-not $composeContent -or $composeContent.Trim().Length -eq 0) {
    Write-Host "ERROR: downloaded compose template is empty." -ForegroundColor Red
    exit 1
}

$composeContent | docker compose -f - @ComposeArgs
exit $LASTEXITCODE