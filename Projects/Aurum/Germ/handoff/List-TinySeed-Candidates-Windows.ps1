[CmdletBinding()]
param(
    [string[]]$ProtectedSerial = @()
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$protected = @{}
foreach ($item in $ProtectedSerial) {
    $value = ([string]$item).Trim()
    if ($value) { $protected[$value] = $true }
}

$candidates = @(Get-Disk | Where-Object { $_.BusType -eq 'USB' } | ForEach-Object {
    $serial = ([string]$_.SerialNumber).Trim()
    $reasons = New-Object System.Collections.Generic.List[string]
    if (-not $serial) { [void]$reasons.Add('serial-missing') }
    if ([bool]$_.IsBoot -or [bool]$_.IsSystem) { [void]$reasons.Add('boot-or-system') }
    if ([bool]$_.IsReadOnly) { [void]$reasons.Add('read-only') }
    if ($serial -and $protected.ContainsKey($serial)) { [void]$reasons.Add('protected-recovery-media') }

    [pscustomobject]@{
        DiskNumber = [int]$_.Number
        FriendlyName = [string]$_.FriendlyName
        SerialNumber = $serial
        SizeBytes = [int64]$_.Size
        IsBoot = [bool]$_.IsBoot
        IsSystem = [bool]$_.IsSystem
        IsReadOnly = [bool]$_.IsReadOnly
        EligibleForTinySeedTest = ($reasons.Count -eq 0)
        RefusalReasons = ($reasons -join ',')
    }
})

if ($candidates.Count -eq 0) {
    Write-Host 'AURUM_TINYSEED_USB_DISCOVERY count=0 state=NO_USB_CANDIDATES'
    exit 0
}

$candidates | Sort-Object DiskNumber | Format-Table -AutoSize
$eligible = @($candidates | Where-Object { $_.EligibleForTinySeedTest })
Write-Host "AURUM_TINYSEED_USB_DISCOVERY count=$($candidates.Count) eligible=$($eligible.Count)"

foreach ($disk in $eligible) {
    Write-Host "AURUM_TINYSEED_USB_CANDIDATE disk=$($disk.DiskNumber) serial=$($disk.SerialNumber) bytes=$($disk.SizeBytes) model=$($disk.FriendlyName)"
}

if ($eligible.Count -eq 1) {
    Write-Host "AURUM_TINYSEED_USB_UNIQUE_CANDIDATE serial=$($eligible[0].SerialNumber) state=SAFE_TO_PREFLIGHT_ONLY"
} elseif ($eligible.Count -gt 1) {
    Write-Host 'AURUM_TINYSEED_USB_SELECTION_REQUIRED state=AMBIGUOUS_MULTIPLE_ELIGIBLE'
}
