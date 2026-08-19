#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = 'FormatX66/BoxBrain'
$runnerRoot = 'C:\actions-runner'
$runnerName = "AURUM-$env:COMPUTERNAME"
$requiredLabel = 'aurum-elevated'

function Get-AurumService {
    @(Get-CimInstance Win32_Service -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -like 'actions.runner.*' -and (
            $_.Name -like "*$runnerName*" -or $_.PathName -match [regex]::Escape($runnerRoot)
        )
    }) | Select-Object -First 1
}

function Get-GhExe {
    $cmd = Get-Command gh -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in @('C:\Program Files\GitHub CLI\gh.exe','C:\Program Files (x86)\GitHub CLI\gh.exe')) {
        if (Test-Path -LiteralPath $p) { return $p }
    }
    return $null
}

function Get-GitHubRunner([string]$GhExe) {
    if (-not $GhExe) { return $null }
    & $GhExe auth status -h github.com *> $null
    if ($LASTEXITCODE -ne 0) { return $null }
    try {
        $json = & $GhExe api "repos/$repo/actions/runners?per_page=100"
        if ($LASTEXITCODE -ne 0 -or -not $json) { return $null }
        $payload = $json | ConvertFrom-Json
        return @($payload.runners | Where-Object { $_.name -eq $runnerName } | Select-Object -First 1)
    } catch {
        return $null
    }
}

function Get-RecentDiagTail {
    $diag = Join-Path $runnerRoot '_diag'
    if (-not (Test-Path -LiteralPath $diag)) { return @() }
    $file = Get-ChildItem -LiteralPath $diag -File -Filter '*.log' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    if (-not $file) { return @() }
    return @(Get-Content -LiteralPath $file.FullName -Tail 80 -ErrorAction SilentlyContinue | Where-Object {
        $_ -match '(?i)(error|fail|exception|offline|connect|listener|session|broker|oauth|credential|forbidden|unauthorized)'
    } | Select-Object -Last 30)
}

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'AURUM_PREFLIGHT_REQUIRES_ADMIN'
}

$checks = [ordered]@{}
$checks.host = $env:COMPUTERNAME
$checks.identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$checks.runner_name = $runnerName
$checks.runner_root_exists = Test-Path -LiteralPath $runnerRoot
$checks.runner_config_exists = Test-Path -LiteralPath (Join-Path $runnerRoot '.runner')
$checks.runner_credentials_exist = Test-Path -LiteralPath (Join-Path $runnerRoot '.credentials')
$checks.github_443 = [bool](Test-NetConnection github.com -Port 443 -InformationLevel Quiet -WarningAction SilentlyContinue)
$checks.api_github_443 = [bool](Test-NetConnection api.github.com -Port 443 -InformationLevel Quiet -WarningAction SilentlyContinue)

$serviceInfo = Get-AurumService
$service = $null
if ($serviceInfo) {
    $service = Get-Service -Name $serviceInfo.Name
    $checks.service_name = [string]$serviceInfo.Name
    $checks.service_state = [string]$service.Status
    $checks.service_start_mode = [string]$serviceInfo.StartMode
    $checks.service_account = [string]$serviceInfo.StartName
    $checks.service_path = [string]$serviceInfo.PathName
} else {
    $checks.service_name = $null
    $checks.service_state = 'Missing'
    $checks.service_start_mode = $null
    $checks.service_account = $null
    $checks.service_path = $null
}

$ghExe = Get-GhExe
$checks.gh_available = [bool]$ghExe
$checks.gh_authenticated = $false
if ($ghExe) {
    & $ghExe auth status -h github.com *> $null
    $checks.gh_authenticated = ($LASTEXITCODE -eq 0)
}

$remote = Get-GitHubRunner $ghExe
if ($remote) {
    $checks.github_runner_found = $true
    $checks.github_runner_id = $remote.id
    $checks.github_runner_status = [string]$remote.status
    $checks.github_runner_busy = [bool]$remote.busy
    $checks.github_runner_labels = @($remote.labels | ForEach-Object { $_.name })
} else {
    $checks.github_runner_found = $false
    $checks.github_runner_id = $null
    $checks.github_runner_status = 'unknown'
    $checks.github_runner_busy = $false
    $checks.github_runner_labels = @()
}

# One bounded self-recovery attempt: if the service exists but GitHub does not see it online,
# restart the service once, then re-query the control plane.
$restarted = $false
if ($service -and $service.Status -eq 'Running' -and $checks.gh_authenticated -and
    ($checks.github_runner_status -ne 'online')) {
    Restart-Service -Name $service.Name -Force
    (Get-Service -Name $service.Name).WaitForStatus('Running', [TimeSpan]::FromSeconds(20))
    $restarted = $true
    Start-Sleep -Seconds 8
    $remote = Get-GitHubRunner $ghExe
    if ($remote) {
        $checks.github_runner_found = $true
        $checks.github_runner_id = $remote.id
        $checks.github_runner_status = [string]$remote.status
        $checks.github_runner_busy = [bool]$remote.busy
        $checks.github_runner_labels = @($remote.labels | ForEach-Object { $_.name })
    }
}
$checks.service_restarted_once = $restarted

$diagTail = Get-RecentDiagTail
$checks.diag_relevant_tail = $diagTail

$labelOkay = @($checks.github_runner_labels) -contains $requiredLabel
$ready = (
    $checks.runner_config_exists -and
    $checks.runner_credentials_exist -and
    $checks.service_state -eq 'Running' -and
    $checks.service_account -match '(?i)(LocalSystem|NT AUTHORITY\\SYSTEM)' -and
    $checks.github_443 -and
    $checks.api_github_443 -and
    $checks.github_runner_found -and
    $checks.github_runner_status -eq 'online' -and
    $labelOkay
)

if ($ready) {
    $marker = 'AURUM_RUNNER_PREFLIGHT_READY'
    $next = 'GitHub dispatch path is healthy; queued elevated Aurum jobs may proceed.'
} elseif (-not $serviceInfo) {
    $marker = 'AURUM_RUNNER_PREFLIGHT_BLOCKED'
    $next = 'Runner service is missing.'
} elseif ($checks.service_state -ne 'Running') {
    $marker = 'AURUM_RUNNER_PREFLIGHT_BLOCKED'
    $next = 'Runner service exists but is not running.'
} elseif (-not $checks.gh_authenticated) {
    $marker = 'AURUM_RUNNER_PREFLIGHT_BLOCKED'
    $next = 'GitHub CLI authentication is unavailable for control-plane verification.'
} elseif (-not $checks.github_runner_found) {
    $marker = 'AURUM_RUNNER_PREFLIGHT_BLOCKED'
    $next = 'Local runner exists but the matching GitHub registration was not found.'
} elseif ($checks.github_runner_status -ne 'online') {
    $marker = 'AURUM_RUNNER_PREFLIGHT_BLOCKED'
    $next = 'Runner service is local-running but GitHub still reports it offline; inspect diag_relevant_tail.'
} elseif (-not $labelOkay) {
    $marker = 'AURUM_RUNNER_PREFLIGHT_BLOCKED'
    $next = "Runner is online but missing required label $requiredLabel."
} else {
    $marker = 'AURUM_RUNNER_PREFLIGHT_BLOCKED'
    $next = 'An unclassified preflight condition remains; inspect checks.'
}

$result = [pscustomobject]@{
    marker = $marker
    ready = $ready
    next = $next
    checks = [pscustomobject]$checks
    observed_at = (Get-Date).ToUniversalTime().ToString('o')
}
$result | ConvertTo-Json -Depth 8
