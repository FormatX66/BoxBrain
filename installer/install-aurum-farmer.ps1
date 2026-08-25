#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "BoxBrain\AurumFarmer"),
    [string]$TaskName = "Aurum Farmer",
    [switch]$SkipStart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$sourceRoot = Join-Path $repositoryRoot "Projects\AurumFarmer"
$python = (Get-Command python.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$sourceCommit = (& git -C $repositoryRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($sourceCommit)) {
    throw "Could not resolve the BoxBrain source commit."
}

$releaseId = "{0}-{1}" -f (Get-Date -Format "yyyyMMddHHmmss"), $sourceCommit.Substring(0, 12)
$releaseRoot = Join-Path $InstallRoot (Join-Path "releases" $releaseId)
$runtimeRoot = Join-Path $InstallRoot "runtime"
$configPath = Join-Path $runtimeRoot "farmer.json"
$receiptPath = Join-Path $runtimeRoot "install-receipt.json"

New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $sourceRoot "aurum_farmer") -Destination $releaseRoot -Recurse
Copy-Item -LiteralPath (Join-Path $sourceRoot "tests") -Destination $releaseRoot -Recurse

$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = $releaseRoot
    & $python -m unittest discover -s (Join-Path $releaseRoot "tests") -v
    if ($LASTEXITCODE -ne 0) { throw "Installed Farmer release tests failed." }
    & $python -m aurum_farmer --config $configPath init --root $runtimeRoot | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Farmer runtime initialization failed." }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}

$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$identity = "{0}\{1}" -f $env:USERDOMAIN, $env:USERNAME
foreach ($secretPath in @([string]$config.api_token_path, [string]$config.signing_key_path)) {
    if (-not (Test-Path -LiteralPath $secretPath -PathType Leaf)) {
        throw "Expected Farmer secret file is missing: $secretPath"
    }
    & icacls.exe $secretPath /inheritance:r /grant:r "${identity}:(F)" "SYSTEM:(F)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not restrict Farmer secret ACL: $secretPath" }
}

$arguments = '-m aurum_farmer --config "{0}" daemon' -f $configPath
$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $releaseRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing -and $existing.State -eq "Running") {
    Stop-ScheduledTask -TaskName $TaskName
}
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings `
    -Description "Persistent Aurum/BoxBrain Farmer supervisor and watchdog." -Force | Out-Null

$healthy = $false
if (-not $SkipStart.IsPresent) {
    Start-ScheduledTask -TaskName $TaskName
    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 500
        try {
            $health = Invoke-RestMethod -Method Get -Uri ("http://{0}:{1}/health" -f $config.api_host, $config.api_port) -TimeoutSec 2
            $healthy = $health.status -eq "healthy" -and $health.event_chain_valid -eq $true
        }
        catch {
            $healthy = $false
        }
    } until ($healthy -or (Get-Date) -ge $deadline)
    if (-not $healthy) { throw "Aurum Farmer task started but the loopback health gate did not pass." }
}

$task = Get-ScheduledTask -TaskName $TaskName
$receipt = [ordered]@{
    schema = "aurum.farmer.install-receipt.v1"
    installed_at = (Get-Date).ToUniversalTime().ToString("o")
    source_commit = $sourceCommit
    release_root = $releaseRoot
    runtime_root = $runtimeRoot
    task_name = $TaskName
    task_state = [string]$task.State
    health_verified = $healthy
    previous_releases_preserved = $true
}
$receipt | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $receiptPath -Encoding utf8
$receipt | ConvertTo-Json -Depth 4
