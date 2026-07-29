[CmdletBinding()]
param(
    [string]$VmName = 'BoxBrain-Windows-Lab',
    [string]$SnapshotName = 'clean-linked-2026-07-29',
    [string]$StatusPath = 'C:\VMs\BoxBrain-Windows-Lab\checkpoint-status.json',
    [string]$ErrorPath = 'C:\VMs\BoxBrain-Windows-Lab\logs\checkpoint-error.json',
    [int]$ShutdownTimeoutSeconds = 180,
    [switch]$RecordExisting
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

trap {
    [ordered]@{
        recorded_at = (Get-Date).ToUniversalTime().ToString('o')
        vm_name = $VmName
        checkpoint_name = $SnapshotName
        error = $_.Exception.Message
        category = $_.CategoryInfo.Category.ToString()
        script_line = $_.InvocationInfo.ScriptLineNumber
    } | ConvertTo-Json | Set-Content -LiteralPath $ErrorPath -Encoding UTF8
    throw
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated Windows PowerShell session.'
}
if ($SnapshotName -notmatch '^[A-Za-z0-9._-]{1,80}$') {
    throw 'SnapshotName contains unsupported characters.'
}

Import-Module Hyper-V -ErrorAction Stop
$vm = Get-VM -Name $VmName -ErrorAction Stop
$existing = @(Get-VMSnapshot -VMName $VmName -ErrorAction SilentlyContinue |
    Where-Object Name -eq $SnapshotName)
if ($existing.Count -gt 1) {
    throw "Multiple checkpoints unexpectedly use this name: $SnapshotName"
}
if ($existing.Count -eq 1 -and -not $RecordExisting) {
    throw "Refusing to replace existing checkpoint: $SnapshotName"
}

if ($vm.State -eq 'Running') {
    Stop-VM -Name $VmName -ErrorAction Stop
    $deadline = (Get-Date).AddSeconds($ShutdownTimeoutSeconds)
    do {
        Start-Sleep -Seconds 2
        $vm = Get-VM -Name $VmName
        if ($vm.State -eq 'Off') {
            break
        }
    } while ((Get-Date) -lt $deadline)
}

if ($vm.State -ne 'Off') {
    throw "Guest did not reach a clean powered-off state; current state is $($vm.State)."
}

if ($existing.Count -eq 0) {
    Checkpoint-VM -Name $VmName -SnapshotName $SnapshotName
    $checkpoint = Get-VMSnapshot -VMName $VmName -Name $SnapshotName -ErrorAction Stop
} else {
    $checkpoint = $existing[0]
}

$status = [ordered]@{
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
    vm_name = $VmName
    vm_state = (Get-VM -Name $VmName).State.ToString()
    checkpoint_name = $checkpoint.Name
    checkpoint_type = $checkpoint.CheckpointType.ToString()
    creation_time_utc = $checkpoint.CreationTime.ToUniversalTime().ToString('o')
    parent_checkpoint_id = if ($checkpoint.PSObject.Properties['ParentSnapshotId']) {
        $checkpoint.ParentSnapshotId
    } else {
        $null
    }
}
$status | ConvertTo-Json | Set-Content -LiteralPath $StatusPath -Encoding UTF8
$status | ConvertTo-Json
