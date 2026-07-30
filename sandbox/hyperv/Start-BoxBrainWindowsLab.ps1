[CmdletBinding()]
param(
    [string]$VmName = 'BoxBrain-Windows-Lab',
    [string]$StatusPath = 'C:\VMs\BoxBrain-Windows-Lab\install-status.json',
    [string]$ErrorPath = 'C:\VMs\BoxBrain-Windows-Lab\logs\start-error.json',
    [switch]$OpenConsole
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

trap {
    [ordered]@{
        recorded_at = (Get-Date).ToUniversalTime().ToString('o')
        vm_name = $VmName
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

Import-Module Hyper-V -ErrorAction Stop
$vm = Get-VM -Name $VmName -ErrorAction Stop
if ($vm.State -eq 'Off') {
    Start-VM -Name $VmName | Out-Null
} elseif ($vm.State -ne 'Running') {
    throw "VM cannot start from state $($vm.State)."
}

$runningVm = Get-VM -Name $VmName
$status = [ordered]@{
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
    vm_name = $VmName
    state = $runningVm.State.ToString()
    status = $runningVm.Status
    uptime_seconds = [math]::Floor($runningVm.Uptime.TotalSeconds)
}
$status | ConvertTo-Json | Set-Content -LiteralPath $StatusPath -Encoding UTF8
$status | ConvertTo-Json

if ($OpenConsole) {
    $vmConnect = Join-Path $env:SystemRoot 'System32\vmconnect.exe'
    Start-Process -FilePath $vmConnect -ArgumentList 'localhost', $VmName
}
