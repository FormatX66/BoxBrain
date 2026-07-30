[CmdletBinding()]
param(
    [string]$VmName = 'BoxBrain-Windows-Lab',
    [string]$UserName = [Security.Principal.WindowsIdentity]::GetCurrent().Name,
    [string]$StatusPath = 'C:\VMs\BoxBrain-Windows-Lab\console-access.json'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated Windows PowerShell session.'
}
if ([string]::IsNullOrWhiteSpace($UserName)) {
    throw 'UserName is required.'
}

Import-Module Hyper-V -ErrorAction Stop
$vm = Get-VM -Name $VmName -ErrorAction Stop
Grant-VMConnectAccess -VMId $vm.Id -UserName $UserName
$access = @(
    Get-VMConnectAccess -VMId $vm.Id -UserName $UserName
)
if ($access.Count -ne 1) {
    throw "Expected one VM console access entry for '$UserName'; found $($access.Count)."
}

$status = [ordered]@{
    granted_at = (Get-Date).ToUniversalTime().ToString('o')
    vm_name = $VmName
    vm_id = $vm.Id.ToString()
    user_name = $UserName
    scope = 'VM console access only'
    hyper_v_administrators_membership_changed = $false
}
$status | ConvertTo-Json | Set-Content -LiteralPath $StatusPath -Encoding UTF8
$status | ConvertTo-Json
