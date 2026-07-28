#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8080
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$controllerDirectory = Join-Path $repositoryRoot "controller"
$python = Join-Path $controllerDirectory ".venv\Scripts\python.exe"
$dashboardDirectory = Join-Path $repositoryRoot "ui\build\web"
$certificatePath = Join-Path $controllerDirectory "data\tls\server-cert.pem"
$privateKeyPath = Join-Path $controllerDirectory "data\tls\server-key.pem"
$serverScript = Join-Path $PSScriptRoot "serve_dashboard.py"

foreach ($requiredPath in @(
    $python,
    $dashboardDirectory,
    $certificatePath,
    $privateKeyPath,
    $serverScript
)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required HTTPS dashboard path is missing: $requiredPath"
    }
}

Write-Host "[starting] BoxBrain dashboard on https://127.0.0.1:$Port"
& $python $serverScript `
    --directory $dashboardDirectory `
    --host 127.0.0.1 `
    --port $Port `
    --certfile $certificatePath `
    --keyfile $privateKeyPath
exit $LASTEXITCODE
