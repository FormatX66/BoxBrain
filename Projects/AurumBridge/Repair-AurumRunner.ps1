#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-AurumRunnerServices {
    @(Get-CimInstance Win32_Service | Where-Object {
        $_.Name -like 'actions.runner.*' -or $_.PathName -match 'RunnerService\.exe'
    })
}

function Find-ConfiguredRunnerRoot {
    $roots = @(
        'C:\actions-runner',
        'C:\Aurum\actions-runner',
        'C:\AurumRunner',
        (Join-Path $env:ProgramData 'Aurum'),
        $env:USERPROFILE
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

    foreach ($root in $roots) {
        $candidate = Get-ChildItem -LiteralPath $root -Filter '.runner' -File -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($candidate) { return $candidate.Directory.FullName }
    }
    return $null
}

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'AURUM_RUNNER_REPAIR_REQUIRES_ADMIN'
}

# Force array semantics even when exactly one runner service exists. PowerShell
# otherwise unwraps a one-item function result into a scalar, which has no
# .Count property under StrictMode.
$services = @(Get-AurumRunnerServices)
if ($services.Count -eq 0) {
    $runnerRoot = Find-ConfiguredRunnerRoot
    if (-not $runnerRoot) {
        throw 'AURUM_RUNNER_NOT_FOUND no-service-and-no-configured-runner-root'
    }

    $svcCmd = Join-Path $runnerRoot 'svc.cmd'
    if (-not (Test-Path -LiteralPath $svcCmd)) {
        throw "AURUM_RUNNER_SERVICE_SCRIPT_MISSING root=$runnerRoot"
    }

    Push-Location $runnerRoot
    try {
        & $svcCmd install
        if ($LASTEXITCODE -ne 0) { throw "AURUM_RUNNER_SERVICE_INSTALL_FAILED exit=$LASTEXITCODE" }
        & $svcCmd start
        if ($LASTEXITCODE -ne 0) { throw "AURUM_RUNNER_SERVICE_START_FAILED exit=$LASTEXITCODE" }
    }
    finally { Pop-Location }

    Start-Sleep -Seconds 2
    $services = @(Get-AurumRunnerServices)
}

if ($services.Count -eq 0) { throw 'AURUM_RUNNER_SERVICE_STILL_MISSING' }

foreach ($svcInfo in $services) {
    $name = [string]$svcInfo.Name
    Set-Service -Name $name -StartupType Automatic

    $svc = Get-Service -Name $name
    if ($svc.Status -eq 'Running') {
        Restart-Service -Name $name -Force
    } else {
        Start-Service -Name $name
    }

    $svc = Get-Service -Name $name
    $svc.WaitForStatus('Running', [TimeSpan]::FromSeconds(20))

    # Ask Windows to restart the runner automatically if the process later fails.
    & sc.exe failure $name reset= 86400 actions= restart/5000/restart/15000/restart/60000 | Out-Null
    & sc.exe failureflag $name 1 | Out-Null
}

$github443 = $false
try {
    $github443 = [bool](Test-NetConnection github.com -Port 443 -InformationLevel Quiet -WarningAction SilentlyContinue)
} catch { $github443 = $false }

$serviceState = @(Get-AurumRunnerServices | ForEach-Object {
    $runtime = Get-Service -Name $_.Name
    [pscustomobject]@{
        name = $_.Name
        state = [string]$runtime.Status
        start_mode = [string]$_.StartMode
        account = [string]$_.StartName
        path = [string]$_.PathName
    }
})

$usb = @(Get-Disk -ErrorAction SilentlyContinue | Where-Object { $_.BusType -eq 'USB' } | ForEach-Object {
    [pscustomobject]@{
        number = $_.Number
        model = $_.FriendlyName
        serial = $_.SerialNumber
        size_bytes = $_.Size
        is_boot = $_.IsBoot
        is_system = $_.IsSystem
        is_offline = $_.IsOffline
    }
})

$result = [pscustomobject]@{
    marker = 'AURUM_RUNNER_REPAIR_OK'
    host = $env:COMPUTERNAME
    identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    github_https_443 = $github443
    services = $serviceState
    usb_disks = $usb
    observed_at = (Get-Date).ToUniversalTime().ToString('o')
}

$result | ConvertTo-Json -Depth 6
