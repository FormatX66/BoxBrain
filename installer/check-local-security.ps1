#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ControllerUrl,
    [string]$DashboardUrl
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$tokenPath = Join-Path $repositoryRoot "controller\data\boxbrain-api-token.local"
$certificatePath = Join-Path $repositoryRoot "controller\data\tls\server-cert.pem"
$privateKeyPath = Join-Path $repositoryRoot "controller\data\tls\server-key.pem"
$certificatePresent = Test-Path -LiteralPath $certificatePath
$privateKeyPresent = Test-Path -LiteralPath $privateKeyPath
if ($certificatePresent -ne $privateKeyPresent) {
    throw "Local TLS configuration is incomplete. Run setup-local-tls.ps1 again."
}
$tlsConfigured = $certificatePresent -and $privateKeyPresent

if ([string]::IsNullOrWhiteSpace($ControllerUrl)) {
    $ControllerUrl = if ($tlsConfigured) {
        "https://127.0.0.1:8000"
    }
    else {
        "http://127.0.0.1:8000"
    }
}
if ([string]::IsNullOrWhiteSpace($DashboardUrl)) {
    $DashboardUrl = if ($tlsConfigured) {
        "https://127.0.0.1:8080"
    }
    else {
        "http://127.0.0.1:8080"
    }
}
if ($tlsConfigured) {
    $controllerUri = [Uri]$ControllerUrl
    $dashboardUri = [Uri]$DashboardUrl
    if ($controllerUri.Scheme -ne "https" -or
        $dashboardUri.Scheme -ne "https") {
        throw "Local TLS files exist, so both security-check URLs must use HTTPS."
    }
}

if (-not (Test-Path -LiteralPath $tokenPath)) {
    throw "Local API token is missing. Run initialize-local-auth.ps1 first."
}
$token = [IO.File]::ReadAllText($tokenPath).Trim()
$headers = @{ "X-BoxBrain-Token" = $token }

$health = Invoke-RestMethod -Uri "$ControllerUrl/api/v1/health" -TimeoutSec 5
if ($health.status -ne "ok") { throw "Controller health is not OK." }
if (-not $health.authentication_required) { throw "Authentication is not enabled." }
if (-not $health.event_stream_enabled) { throw "Event streaming is not enabled." }
Write-Host "[pass] Public health reports authenticated streaming."

$unauthenticatedStatus = $null
try {
    Invoke-WebRequest -UseBasicParsing -Uri "$ControllerUrl/api/v1/targets" -TimeoutSec 5 | Out-Null
    $unauthenticatedStatus = 200
}
catch {
    if ($null -eq $_.Exception.Response) { throw }
    $unauthenticatedStatus = [int]$_.Exception.Response.StatusCode
}
if ($unauthenticatedStatus -ne 401) {
    throw "Unauthenticated target request returned HTTP $unauthenticatedStatus instead of 401."
}
Write-Host "[pass] Unauthenticated target access is rejected."

$targets = @(Invoke-RestMethod -Uri "$ControllerUrl/api/v1/targets" -Headers $headers -TimeoutSec 5)
if ($targets.Count -ne 1) { throw "Expected one allowlisted target." }
if ($targets[0].input_enabled) { throw "Target input must remain disabled." }
Write-Host "[pass] Authenticated target is allowlisted and read-only."

$stop = Invoke-RestMethod -Uri "$ControllerUrl/api/v1/safety/emergency-stop" -Headers $headers -TimeoutSec 5
Write-Host "[pass] Emergency stop state is readable (engaged=$($stop.engaged), generation=$($stop.generation))."

$dashboard = Invoke-WebRequest -UseBasicParsing -Uri $DashboardUrl -TimeoutSec 5
if ($dashboard.StatusCode -ne 200) { throw "Dashboard did not return HTTP 200." }
Write-Host "[pass] Dashboard is reachable."
if ($tlsConfigured) {
    Write-Host "[pass] Both services use a certificate trusted by this Windows user."
}
Write-Host ""
Write-Host "Local BoxBrain security checks passed. No state was changed."
exit 0
