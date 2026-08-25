#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$TaskName = "Aurum Farmer"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
    if ($task.State -eq "Running") { Stop-ScheduledTask -TaskName $TaskName }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

[ordered]@{
    task_removed = $null -ne $task
    durable_ledger_preserved = $true
    runtime_root = (Join-Path $env:LOCALAPPDATA "BoxBrain\AurumFarmer\runtime")
} | ConvertTo-Json
