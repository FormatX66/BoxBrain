#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-AurumRunnerServices {
    @(Get-CimInstance Win32_Service | Where-Object {
        $_.Name -like 'actions.runner.*' -or $_.PathName -match 'RunnerService\.exe'
    })
}

function Test-RunnerRoot([string]$Path) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $null }
    $runnerFile = Join-Path $Path '.runner'
    $svcCmd = Join-Path $Path 'svc.cmd'
    $listener = Join-Path $Path 'bin\Runner.Listener.exe'
    if ((Test-Path -LiteralPath $runnerFile) -and
        (Test-Path -LiteralPath $svcCmd) -and
        (Test-Path -LiteralPath $listener)) {
        return $Path
    }
    return $null
}

function Find-ConfiguredRunnerRoot {
    $roots = @(
        'C:\actions-runner',
        'C:\Aurum\actions-runner',
        'C:\AurumRunner',
        'C:\GitHubRunner',
        'C:\github-actions-runner',
        (Join-Path $env:ProgramData 'Aurum'),
        $env:USERPROFILE
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

    foreach ($root in $roots) {
        $direct = Test-RunnerRoot $root
        if ($direct) { return $direct }

        $candidate = Get-ChildItem -LiteralPath $root -Filter '.runner' -File -Force -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($candidate) {
            $valid = Test-RunnerRoot $candidate.Directory.FullName
            if ($valid) { return $valid }
        }
    }

    # The original runner may have been extracted to another fixed drive or an
    # unconventional directory. Search every local fixed drive as a final recovery pass.
    $fixed = @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' -ErrorAction SilentlyContinue)
    foreach ($disk in $fixed) {
        $driveRoot = ([string]$disk.DeviceID) + '\'
        Write-Host "AURUM_RUNNER_SEARCH drive=$driveRoot"
        $candidate = Get-ChildItem -LiteralPath $driveRoot -Filter '.runner' -File -Force -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($candidate) {
            $valid = Test-RunnerRoot $candidate.Directory.FullName
            if ($valid) { return $valid }
        }
    }
    return $null
}

function Get-UsbInventory {
    @(Get-Disk -ErrorAction SilentlyContinue | Where-Object { $_.BusType -eq 'USB' } | ForEach-Object {
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
}

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'AURUM_RUNNER_REPAIR_REQUIRES_ADMIN'
}

$github443 = $false
try {
    $github443 = [bool](Test-NetConnection github.com -Port 443 -InformationLevel Quiet -WarningAction SilentlyContinue)
} catch { $github443 = $false }

$services = @(Get-AurumRunnerServices)
$runnerRoot = $null

if ($services.Count -eq 0) {
    $runnerRoot = Find-ConfiguredRunnerRoot
    if ($runnerRoot) {
        Write-Host "AURUM_RUNNER_ROOT_FOUND root=$runnerRoot"
        $svcCmd = Join-Path $runnerRoot 'svc.cmd'
        Push-Location $runnerRoot
        try {
            & $svcCmd install
            if ($LASTEXITCODE -ne 0) { throw "AURUM_RUNNER_SERVICE_INSTALL_FAILED exit=$LASTEXITCODE root=$runnerRoot" }
            & $svcCmd start
            if ($LASTEXITCODE -ne 0) { throw "AURUM_RUNNER_SERVICE_START_FAILED exit=$LASTEXITCODE root=$runnerRoot" }
        }
        finally { Pop-Location }
        Start-Sleep -Seconds 2
        $services = @(Get-AurumRunnerServices)
    }
}

if ($services.Count -gt 0) {
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

        & sc.exe failure $name reset= 86400 actions= restart/5000/restart/15000/restart/60000 | Out-Null
        & sc.exe failureflag $name 1 | Out-Null
    }
}

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

$usb = @(Get-UsbInventory)
$marker = if ($serviceState.Count -gt 0) { 'AURUM_RUNNER_REPAIR_OK' } else { 'AURUM_RUNNER_REINSTALL_REQUIRED' }

$result = [pscustomobject]@{
    marker = $marker
    host = $env:COMPUTERNAME
    identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    github_https_443 = $github443
    configured_runner_root = $runnerRoot
    services = $serviceState
    usb_disks = $usb
    observed_at = (Get-Date).ToUniversalTime().ToString('o')
}

$result | ConvertTo-Json -Depth 6
