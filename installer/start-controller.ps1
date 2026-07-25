#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8000,
    [switch]$DisableTls
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$controllerDirectory = Join-Path $repositoryRoot "controller"
$python = Join-Path $controllerDirectory ".venv\Scripts\python.exe"
$tokenPath = Join-Path $controllerDirectory "data\boxbrain-api-token.local"
$tlsDirectory = Join-Path $controllerDirectory "data\tls"
$certificatePath = Join-Path $tlsDirectory "server-cert.pem"
$privateKeyPath = Join-Path $tlsDirectory "server-key.pem"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Controller virtual environment is missing. Follow docs/DEVELOPMENT.md first."
}
if (-not (Test-Path -LiteralPath $tokenPath)) {
    & (Join-Path $PSScriptRoot "initialize-local-auth.ps1")
}

$token = [IO.File]::ReadAllText($tokenPath).Trim()
if ($token.Length -lt 32) {
    throw "The local API token is invalid. Rotate it with initialize-local-auth.ps1 -Rotate."
}

$env:BOXBRAIN_ENVIRONMENT = "development"
$env:BOXBRAIN_HOST = "127.0.0.1"
$env:BOXBRAIN_PORT = $Port.ToString()
$env:BOXBRAIN_ALLOWED_HOSTS = "127.0.0.1,localhost"
$env:BOXBRAIN_API_TOKEN = $token

$arguments = @(
    "-m",
    "uvicorn",
    "boxbrain_controller.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    $Port
)
$scheme = "http"
if (-not $DisableTls) {
    if (-not (Test-Path -LiteralPath $certificatePath) -or
        -not (Test-Path -LiteralPath $privateKeyPath)) {
        throw "Local TLS files are missing. Run installer/setup-local-tls.ps1 or pass -DisableTls."
    }
    $arguments += @(
        "--ssl-keyfile",
        $privateKeyPath,
        "--ssl-certfile",
        $certificatePath
    )
    $scheme = "https"
}

Write-Host "[starting] BoxBrain controller on ${scheme}://127.0.0.1:$Port"
Write-Host "           Authentication enabled; token value not printed."
Push-Location $controllerDirectory
try {
    & $python @arguments
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $exitCode
