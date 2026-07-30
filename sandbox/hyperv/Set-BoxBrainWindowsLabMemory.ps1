[CmdletBinding()]
param(
    [string]$VmName = 'BoxBrain-Windows-Lab',
    [long]$StartupBytes = 1GB,
    [long]$MinimumBytes = 1GB,
    [long]$MaximumBytes = 4GB,
    [string]$StatusPath = 'C:\VMs\BoxBrain-Windows-Lab\memory-status.json'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated Windows PowerShell session.'
}

if (
    $MinimumBytes -lt 1GB -or
    $StartupBytes -lt $MinimumBytes -or
    $MaximumBytes -lt $StartupBytes -or
    $MaximumBytes -gt 4GB
) {
    throw 'Memory values must satisfy 1 GiB <= minimum <= startup <= maximum <= 4 GiB.'
}

Import-Module Hyper-V -ErrorAction Stop
$vm = Get-VM -Name $VmName -ErrorAction Stop
if ($vm.State -ne 'Off') {
    throw "VM must be off before changing startup memory; current state is $($vm.State)."
}

Set-VMMemory -VMName $VmName -DynamicMemoryEnabled $true `
    -MinimumBytes $MinimumBytes `
    -StartupBytes $StartupBytes `
    -MaximumBytes $MaximumBytes

$memory = Get-VMMemory -VMName $VmName
$status = [ordered]@{
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
    vm_name = $VmName
    dynamic_memory_enabled = $memory.DynamicMemoryEnabled
    minimum_bytes = $memory.Minimum
    startup_bytes = $memory.Startup
    maximum_bytes = $memory.Maximum
}
$status | ConvertTo-Json | Set-Content -LiteralPath $StatusPath -Encoding UTF8
$status | ConvertTo-Json
