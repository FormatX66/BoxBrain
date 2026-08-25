[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$IntentPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [ValidateRange(512, 67108864)]
    [int]$Bytes = 4194304
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Physical-card readback requires an elevated Administrator process.'
}

$intent = Get-Content -Raw -LiteralPath $IntentPath | ConvertFrom-Json
if ($intent.schema -notin @('aurum-pi3-flash-intent-v1', 'aurum-pi3-flash-intent-v2')) {
    throw 'Flash intent schema mismatch.'
}
$diskNumber = [int]$intent.target.disk_number
$canonicalDevice = "\\.\PhysicalDrive$diskNumber"
if ($diskNumber -lt 1 -or $intent.target.device_id -ne $canonicalDevice) {
    throw 'Unsafe or inconsistent physical-card readback target.'
}
$disk = Get-Disk -Number $diskNumber
$drive = Get-CimInstance Win32_DiskDrive -Filter "Index=$diskNumber"
if ($disk.IsBoot -or $disk.IsSystem -or $disk.BusType -ne 'USB' -or
    $disk.Size -ne [long]$intent.target.disk_bytes -or
    $drive.Model -ne $intent.target.model -or
    $drive.PNPDeviceID -ne $intent.target.pnp_device_id) {
    throw 'Physical-card identity changed before readback.'
}

$buffer = [byte[]]::new($Bytes)
$source = [System.IO.FileStream]::new(
    $canonicalDevice,
    [System.IO.FileMode]::Open,
    [System.IO.FileAccess]::Read,
    [System.IO.FileShare]::ReadWrite,
    1048576,
    [System.IO.FileOptions]::SequentialScan
)
try {
    $offset = 0
    while ($offset -lt $Bytes) {
        $read = $source.Read($buffer, $offset, $Bytes - $offset)
        if ($read -eq 0) { throw "Unexpected end of physical card at byte $offset." }
        $offset += $read
    }
}
finally {
    $source.Dispose()
}
[System.IO.File]::WriteAllBytes([System.IO.Path]::GetFullPath($OutputPath), $buffer)
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $OutputPath).Hash.ToLowerInvariant()
Write-Output "AURUM_CARD_PREFIX_READ disk=$diskNumber bytes=$Bytes sha256=$hash path=$OutputPath"
