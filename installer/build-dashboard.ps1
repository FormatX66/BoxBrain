#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ControllerUrl = "http://127.0.0.1:8000"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$uiDirectory = Join-Path $repositoryRoot "ui"
$tokenPath = Join-Path $repositoryRoot "controller\data\boxbrain-api-token.local"

if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) {
    throw "Flutter is not available on PATH."
}
if (-not (Test-Path -LiteralPath $tokenPath)) {
    & (Join-Path $PSScriptRoot "initialize-local-auth.ps1")
}
$token = [IO.File]::ReadAllText($tokenPath).Trim()
if ($token.Length -lt 32) {
    throw "The local API token is invalid. Rotate it with initialize-local-auth.ps1 -Rotate."
}

Push-Location $uiDirectory
try {
    Write-Host "[building] Authenticated BoxBrain dashboard"
    $arguments = @(
        "build",
        "web",
        "--dart-define=BOXBRAIN_API_URL=$ControllerUrl",
        "--dart-define=BOXBRAIN_API_TOKEN=$token"
    )
    & flutter @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Flutter web build failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

Write-Host "[ready] Dashboard build: $uiDirectory\build\web"
Write-Host "        Token value was not printed."