[CmdletBinding()]
param(
    [string]$VmName = 'BoxBrain-Windows-Lab',
    [string]$AnswerIso = 'C:\VMs\BoxBrain-Windows-Lab\media\BoxBrain-Autounattend.iso'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated Windows PowerShell session.'
}

Import-Module Hyper-V -ErrorAction Stop
$vm = Get-VM -Name $VmName -ErrorAction Stop
if ($vm.State -ne 'Off') {
    throw "VM must be powered off before attaching answer media; state is $($vm.State)."
}
$AnswerIso = [IO.Path]::GetFullPath($AnswerIso)
if (-not (Test-Path -LiteralPath $AnswerIso -PathType Leaf)) {
    throw "Answer ISO is missing: $AnswerIso"
}

$dvdDrives = @(Get-VMDvdDrive -VMName $VmName)
$matchingDrive = @($dvdDrives | Where-Object Path -ceq $AnswerIso)
if ($matchingDrive.Count -eq 1) {
    Write-Host '[ready] Answer media is already attached; no changes made.'
    exit 0
}
if ($dvdDrives.Count -ne 1) {
    throw "Expected one Windows installation DVD before attachment; found $($dvdDrives.Count)."
}

Add-VMDvdDrive -VMName $VmName -Path $AnswerIso | Out-Null
Write-Host '[ready] BoxBrain answer media attached as the second DVD.'
