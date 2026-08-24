[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ImagePath,
    [Parameter(Mandatory=$true)][string]$ChecksumPath,
    [Parameter(Mandatory=$true)][string]$DiskSerial,
    [Parameter(Mandatory=$true)][string]$ConfirmText,
    [switch]$Write
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Fail([string]$Reason) {
    Write-Host "AURUM_TINYSEED_FLASH_REFUSED reason=$Reason"
    exit 2
}

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Fail 'administrator-required'
}

$image = Get-Item -LiteralPath $ImagePath -ErrorAction Stop
$sum = Get-Item -LiteralPath $ChecksumPath -ErrorAction Stop
$expected = ((Get-Content -LiteralPath $sum.FullName -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
if ($expected -notmatch '^[0-9a-f]{64}$') { Fail 'invalid-checksum-file' }
$actual = (Get-FileHash -LiteralPath $image.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { Fail 'image-checksum-mismatch' }

$serial = $DiskSerial.Trim()
$matches = @(Get-Disk | Where-Object {
    ([string]$_.SerialNumber).Trim() -eq $serial
})
if ($matches.Count -ne 1) { Fail "disk-serial-not-unique count=$($matches.Count)" }
$disk = $matches[0]
if ($disk.BusType -ne 'USB') { Fail "target-not-usb bus=$($disk.BusType)" }
if ([bool]$disk.IsBoot -or [bool]$disk.IsSystem) { Fail 'target-is-boot-or-system' }
if ([bool]$disk.IsReadOnly) { Fail 'target-is-read-only' }
if ([int64]$disk.Size -le [int64]$image.Length) { Fail 'target-too-small' }

$requiredConfirm = "FLASH_TINYSEED_$($actual.Substring(0,8).ToUpperInvariant())"
if ($ConfirmText -ne $requiredConfirm) {
    Fail "confirmation-mismatch expected=$requiredConfirm"
}

Write-Host "AURUM_TINYSEED_FLASH_PREFLIGHT_OK disk=$($disk.Number) model=$($disk.FriendlyName) serial=$serial bytes=$($image.Length) sha256=$actual"
if (-not $Write) {
    Write-Host 'AURUM_TINYSEED_FLASH_DRY_RUN state=READY_FOR_EXPLICIT_WRITE'
    exit 0
}

$diskNumber = [int]$disk.Number
$physicalPath = "\\.\PhysicalDrive$diskNumber"
$expectedSize = [int64]$disk.Size

# Re-prove identity immediately before any destructive operation.
$live = Get-Disk -Number $diskNumber -ErrorAction Stop
if (
    ([string]$live.SerialNumber).Trim() -ne $serial -or
    [int64]$live.Size -ne $expectedSize -or
    $live.BusType -ne 'USB' -or
    [bool]$live.IsBoot -or
    [bool]$live.IsSystem
) {
    Fail 'target-identity-changed-before-write'
}

$letters = @(Get-Partition -DiskNumber $diskNumber -ErrorAction SilentlyContinue |
    Where-Object { $_.DriveLetter } | ForEach-Object { [string]$_.DriveLetter })
foreach ($letter in $letters) {
    & mountvol "$letter`:" /P | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "volume-dismount-failed drive=$letter" }
}

try {
    Set-Disk -Number $diskNumber -IsOffline $true -ErrorAction Stop
} catch {
    # Windows refuses offline for some removable devices. Identity was already
    # re-proven and volumes were dismounted, so continue only for that known case.
    if ($_.Exception.Message -notmatch '(?i)(removable media cannot be set to offline|not supported)') {
        throw
    }
}

$bufferSize = 4MB
$buffer = New-Object byte[] $bufferSize
$source = [IO.File]::Open($image.FullName, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
try {
    $target = New-Object IO.FileStream(
        $physicalPath,
        [IO.FileMode]::Open,
        [IO.FileAccess]::Write,
        [IO.FileShare]::ReadWrite,
        $bufferSize,
        [IO.FileOptions]::WriteThrough
    )
    try {
        while (($read = $source.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $target.Write($buffer, 0, $read)
        }
        $target.Flush($true)
    } finally {
        $target.Dispose()
    }
} finally {
    $source.Dispose()
}

# Full image-length readback hash. This is deliberately slower than a spot check
# because READY_TO_BOOT should mean the bytes written were actually re-read.
$sha = [Security.Cryptography.SHA256]::Create()
try {
    $reader = New-Object IO.FileStream(
        $physicalPath,
        [IO.FileMode]::Open,
        [IO.FileAccess]::Read,
        [IO.FileShare]::ReadWrite,
        $bufferSize,
        [IO.FileOptions]::SequentialScan
    )
    try {
        $remaining = [int64]$image.Length
        while ($remaining -gt 0) {
            $want = [int][Math]::Min([int64]$buffer.Length, $remaining)
            $read = $reader.Read($buffer, 0, $want)
            if ($read -le 0) { Fail 'unexpected-end-of-device-during-readback' }
            [void]$sha.TransformBlock($buffer, 0, $read, $null, 0)
            $remaining -= $read
        }
        [void]$sha.TransformFinalBlock([byte[]]::new(0), 0, 0)
        $readback = ([BitConverter]::ToString($sha.Hash)).Replace('-', '').ToLowerInvariant()
    } finally {
        $reader.Dispose()
    }
} finally {
    $sha.Dispose()
}

if ($readback -ne $actual) { Fail "raw-readback-mismatch actual=$readback expected=$actual" }
Write-Host "AURUM_TINYSEED_FLASH_OK disk=$diskNumber serial=$serial image_sha256=$actual raw_readback_verified=true"
