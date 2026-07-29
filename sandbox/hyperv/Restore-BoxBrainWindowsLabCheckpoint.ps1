[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [ValidatePattern('^[A-Za-z0-9._-]{1,80}$')]
    [string]$VmName = 'BoxBrain-Windows-Lab',

    [ValidatePattern('^[A-Za-z0-9._-]{1,80}$')]
    [string]$SnapshotName = 'clean-linked-2026-07-29',

    [string]$StatusPath = 'C:\VMs\BoxBrain-Windows-Lab\restore-status.json',

    [switch]$GrantCurrentUserAccess,

    [bool]$StartAfterRestore = $true
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )) {
    throw @'
Windows has not granted administrator authority. Right-click Windows
PowerShell, choose Run as administrator, approve the Windows prompt, and run
this exact script again.
'@
}

Import-Module Hyper-V -ErrorAction Stop

$vm = Get-VM -Name $VmName -ErrorAction Stop
$snapshots = @(
    Get-VMSnapshot -VMName $VmName -ErrorAction Stop |
        Where-Object Name -eq $SnapshotName
)
if ($snapshots.Count -ne 1) {
    throw "Expected exactly one checkpoint named '$SnapshotName'; found $($snapshots.Count)."
}
$snapshot = $snapshots[0]

$action = "Restore checkpoint '$SnapshotName'"
if ($GrantCurrentUserAccess) {
    $action += " and grant '$($identity.Name)' future Hyper-V VM access"
}
if (-not $PSCmdlet.ShouldProcess($VmName, $action)) {
    return
}

$membershipAdded = $false
if ($GrantCurrentUserAccess) {
    $hyperVGroup = Get-LocalGroup -SID 'S-1-5-32-578' -ErrorAction Stop
    $existingMembers = @(
        Get-LocalGroupMember -Group $hyperVGroup -ErrorAction Stop
    )
    if ($identity.Name -notin $existingMembers.Name) {
        Add-LocalGroupMember -Group $hyperVGroup -Member $identity.Name
        $membershipAdded = $true
    }
}

Restore-VMSnapshot `
    -VMName $VmName `
    -Name $SnapshotName `
    -Confirm:$false `
    -ErrorAction Stop

$vm = Get-VM -Name $VmName -ErrorAction Stop
if ($StartAfterRestore -and $vm.State -eq 'Off') {
    Start-VM -Name $VmName -ErrorAction Stop | Out-Null
    $vm = Get-VM -Name $VmName -ErrorAction Stop
}

$status = [ordered]@{
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
    vm_name = $vm.Name
    vm_id = $vm.Id.ToString()
    vm_state = $vm.State.ToString()
    checkpoint_name = $snapshot.Name
    checkpoint_id = $snapshot.Id.ToString()
    checkpoint_created_at = $snapshot.CreationTime.ToUniversalTime().ToString('o')
    current_user = $identity.Name
    hyperv_access_requested = [bool]$GrantCurrentUserAccess
    hyperv_membership_added = $membershipAdded
    new_sign_in_required_for_non_elevated_access = $membershipAdded
    start_after_restore = $StartAfterRestore
}

$statusDirectory = Split-Path -Parent $StatusPath
if (-not (Test-Path -LiteralPath $statusDirectory -PathType Container)) {
    throw "Status directory does not exist: $statusDirectory"
}
$status | ConvertTo-Json | Set-Content -LiteralPath $StatusPath -Encoding UTF8
$status | ConvertTo-Json
