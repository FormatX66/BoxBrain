#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet("Start", "Stop", "Restart", "Status", "Health", "Poll", "DryRun")]
    [string]$Action,
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "BoxBrain\CodexBridge")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$taskName = "BoxBrain Git Local Codex Bridge"
$configPath = Join-Path $InstallRoot "config.json"
$watcherPath = Join-Path $InstallRoot "bin\watch-git-local-codex-bridge.ps1"

switch ($Action) {
    "Start" {
        Start-ScheduledTask -TaskName $taskName
        Start-Sleep -Milliseconds 500
    }
    "Stop" {
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
    }
    "Restart" {
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
        Start-ScheduledTask -TaskName $taskName
        Start-Sleep -Milliseconds 500
    }
    "Poll" {
        $powerShell = (Get-Command powershell.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
        & $powerShell -NoProfile -ExecutionPolicy Bypass `
            -File $watcherPath -ConfigPath $configPath -Mode Once
        exit $LASTEXITCODE
    }
    "DryRun" {
        $powerShell = (Get-Command powershell.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
        & $powerShell -NoProfile -ExecutionPolicy Bypass `
            -File $watcherPath -ConfigPath $configPath -Mode Once -DryRun
        exit $LASTEXITCODE
    }
}

$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
$info = if ($task) { Get-ScheduledTaskInfo -TaskName $taskName } else { $null }
$healthPath = Join-Path $InstallRoot "state\health.json"
$health = if (Test-Path -LiteralPath $healthPath -PathType Leaf) {
    Get-Content -LiteralPath $healthPath -Raw | ConvertFrom-Json
} else { $null }

[pscustomobject]@{
    installed = $null -ne $task
    task_state = if ($task) { [string]$task.State } else { "NotInstalled" }
    last_run_time = if ($info) { $info.LastRunTime } else { $null }
    last_task_result = if ($info) { $info.LastTaskResult } else { $null }
    health_status = if ($health) { $health.status } else { "unknown" }
    health_timestamp = if ($health) { $health.timestamp } else { $null }
    pending_count = if ($health) { $health.pending_count } else { $null }
}
