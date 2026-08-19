#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = 'FormatX66/BoxBrain'
$repoUrl = 'https://github.com/FormatX66/BoxBrain'
$runnerRoot = 'C:\actions-runner'
$runnerName = $env:COMPUTERNAME
$customLabel = 'aurum-elevated'

function Ensure-GhCli {
    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if ($gh) { return $gh.Source }

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw 'AURUM_RUNNER_BOOTSTRAP_NEEDS_GH_OR_WINGET'
    }

    Write-Host 'AURUM_RUNNER_BOOTSTRAP installing=GitHub.cli'
    & winget install --id GitHub.cli --exact --silent --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw "AURUM_GH_INSTALL_FAILED exit=$LASTEXITCODE" }

    $candidates = @(
        'C:\Program Files\GitHub CLI\gh.exe',
        'C:\Program Files (x86)\GitHub CLI\gh.exe'
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }

    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $gh) { throw 'AURUM_GH_INSTALL_NOT_DISCOVERABLE' }
    return $gh.Source
}

function Ensure-GhAuth([string]$GhExe) {
    & $GhExe auth status -h github.com *> $null
    if ($LASTEXITCODE -eq 0) { return }

    Write-Host 'AURUM_RUNNER_BOOTSTRAP_AUTH_REQUIRED'
    Write-Host 'A browser/device authorization may open. Complete the GitHub login for FormatX66, then return here.'
    & $GhExe auth login --hostname github.com --git-protocol https --web
    if ($LASTEXITCODE -ne 0) { throw "AURUM_GH_AUTH_FAILED exit=$LASTEXITCODE" }
}

function Get-RegistrationToken([string]$GhExe) {
    $token = (& $GhExe api --method POST "repos/$repo/actions/runners/registration-token" --jq '.token').Trim()
    if ($LASTEXITCODE -ne 0 -or -not $token) {
        throw 'AURUM_RUNNER_REGISTRATION_TOKEN_FAILED'
    }
    return $token
}

function Get-LatestRunnerAsset {
    $release = Invoke-RestMethod -Headers @{ 'User-Agent' = 'AurumRunnerBootstrap' } -Uri 'https://api.github.com/repos/actions/runner/releases/latest'
    $asset = @($release.assets | Where-Object { $_.name -match '^actions-runner-win-x64-.*\.zip$' } | Select-Object -First 1)
    if ($asset.Count -ne 1) { throw 'AURUM_RUNNER_ASSET_NOT_FOUND' }
    return $asset[0]
}

function Prepare-RunnerRoot {
    if (Test-Path -LiteralPath $runnerRoot) {
        $entries = @(Get-ChildItem -LiteralPath $runnerRoot -Force -ErrorAction SilentlyContinue)
        if ($entries.Count -gt 0) {
            $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
            $backup = "$runnerRoot-backup-$stamp"
            Move-Item -LiteralPath $runnerRoot -Destination $backup
            Write-Host "AURUM_RUNNER_BOOTSTRAP backup=$backup"
        }
    }
    New-Item -ItemType Directory -Path $runnerRoot -Force | Out-Null
}

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'AURUM_RUNNER_BOOTSTRAP_REQUIRES_ADMIN'
}

$usb = @(Get-Disk -ErrorAction SilentlyContinue | Where-Object { $_.BusType -eq 'USB' -and -not $_.IsBoot -and -not $_.IsSystem })
Write-Host "AURUM_RUNNER_BOOTSTRAP_HOST host=$env:COMPUTERNAME usb_safe_count=$($usb.Count)"
foreach ($disk in $usb) {
    Write-Host "AURUM_RUNNER_BOOTSTRAP_USB disk=$($disk.Number) model=$($disk.FriendlyName) serial=$($disk.SerialNumber) size=$($disk.Size)"
}

$ghExe = Ensure-GhCli
Ensure-GhAuth $ghExe
$registrationToken = Get-RegistrationToken $ghExe
$asset = Get-LatestRunnerAsset
Prepare-RunnerRoot

$zip = Join-Path $env:TEMP $asset.name
Write-Host "AURUM_RUNNER_BOOTSTRAP_DOWNLOAD asset=$($asset.name)"
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip
Expand-Archive -LiteralPath $zip -DestinationPath $runnerRoot -Force

Push-Location $runnerRoot
try {
    & .\config.cmd --unattended --url $repoUrl --token $registrationToken --name $runnerName --labels $customLabel --work '_work' --runasservice
    if ($LASTEXITCODE -ne 0) { throw "AURUM_RUNNER_CONFIG_FAILED exit=$LASTEXITCODE" }
}
finally {
    Pop-Location
}

$services = @(Get-CimInstance Win32_Service | Where-Object { $_.Name -like 'actions.runner.*' -and $_.PathName -match [regex]::Escape($runnerRoot) })
if ($services.Count -eq 0) {
    $services = @(Get-CimInstance Win32_Service | Where-Object { $_.Name -like 'actions.runner.*' })
}
if ($services.Count -eq 0) { throw 'AURUM_RUNNER_SERVICE_NOT_CREATED' }

foreach ($svcInfo in $services) {
    $name = [string]$svcInfo.Name
    Stop-Service -Name $name -Force -ErrorAction SilentlyContinue
    & sc.exe config $name obj= LocalSystem | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "AURUM_RUNNER_SYSTEM_ACCOUNT_CONFIG_FAILED service=$name exit=$LASTEXITCODE" }
    Set-Service -Name $name -StartupType Automatic
    & sc.exe failure $name reset= 86400 actions= restart/5000/restart/15000/restart/60000 | Out-Null
    & sc.exe failureflag $name 1 | Out-Null
    Start-Service -Name $name
    (Get-Service -Name $name).WaitForStatus('Running', [TimeSpan]::FromSeconds(20))
}

Start-Sleep -Seconds 3
$state = @(Get-CimInstance Win32_Service | Where-Object { $_.Name -like 'actions.runner.*' } | ForEach-Object {
    $runtime = Get-Service -Name $_.Name
    [pscustomobject]@{
        name = $_.Name
        state = [string]$runtime.Status
        start_mode = [string]$_.StartMode
        account = [string]$_.StartName
        path = [string]$_.PathName
    }
})

$result = [pscustomobject]@{
    marker = 'AURUM_RUNNER_BOOTSTRAP_OK'
    host = $env:COMPUTERNAME
    runner_root = $runnerRoot
    runner_name = $runnerName
    label = $customLabel
    services = $state
    usb_disks = @($usb | ForEach-Object {
        [pscustomobject]@{
            number = $_.Number
            model = $_.FriendlyName
            serial = $_.SerialNumber
            size_bytes = $_.Size
        }
    })
    observed_at = (Get-Date).ToUniversalTime().ToString('o')
}
$result | ConvertTo-Json -Depth 6
