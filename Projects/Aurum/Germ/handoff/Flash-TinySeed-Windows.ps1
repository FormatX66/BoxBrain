[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ImagePath,
    [Parameter(Mandatory=$true)][string]$ChecksumPath,
    [Parameter(Mandatory=$true)][string]$DiskSerial,
    [Parameter(Mandatory=$true)][string]$ConfirmText,
    [string[]]$ProtectedSerial = @(),
    [switch]$Write
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Fail([string]$Reason) {
    Write-Host "AURUM_TINYSEED_FLASH_REFUSED reason=$Reason"
    exit 2
}

$protected = @{}
foreach ($item in $ProtectedSerial) {
    $value = ([string]$item).Trim()
    if ($value) { $protected[$value] = $true }
}

# When running from a BoxBrain checkout, automatically import the canonical
# protected-media registry so known recovery media cannot be selected even if a
# caller forgets to pass -ProtectedSerial explicitly.
$registryPath = Join-Path $PSScriptRoot '..\..\Recovery\protected-media.json'
if (Test-Path -LiteralPath $registryPath) {
    try {
        $registry = Get-Content -LiteralPath $registryPath -Raw | ConvertFrom-Json
        foreach ($device in @($registry.devices)) {
            if ([bool]$device.protected) {
                $value = ([string]$device.serial).Trim()
                if ($value) { $protected[$value] = $true }
            }
        }
    } catch {
        Fail 'protected-media-registry-invalid'
    }
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
if (-not $serial) { Fail 'disk-serial-missing' }
if ($protected.ContainsKey($serial)) { Fail 'target-is-protected-recovery-media' }

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
if ($protected.ContainsKey(([string]$live.SerialNumber).Trim())) {
    Fail 'target-became-protected-before-write'
}

$letters = @(Get-Partition -DiskNumber $diskNumber -ErrorAction SilentlyContinue |
    Where-Object { $_.DriveLetter } | ForEach-Object { [string]$_.DriveLetter })
foreach ($letter in $letters) {
    & mountvol "$letter`:" /P | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "volume-dismount-failed drive=$letter" }
}

$removableRequiresClean = $false
try {
    Set-Disk -Number $diskNumber -IsOffline $true -ErrorAction Stop
} catch {
    # Windows refuses offline for some removable devices. Identity was already
    # re-proven and volumes were dismounted, so continue only for that known case.
    if ($_.Exception.Message -notmatch '(?i)(removable media cannot be set to offline|not supported)') {
        throw
    }
    $removableRequiresClean = $true
}

if ($removableRequiresClean) {
    # A letterless mounted volume can remain after drive-letter dismount and
    # block raw writes even for an elevated process. Re-prove the exact target,
    # then clear only its stale partition map so Windows releases that volume.
    $live = Get-Disk -Number $diskNumber -ErrorAction Stop
    if (
        ([string]$live.SerialNumber).Trim() -ne $serial -or
        [int64]$live.Size -ne $expectedSize -or
        $live.BusType -ne 'USB' -or
        [bool]$live.IsBoot -or
        [bool]$live.IsSystem -or
        [bool]$live.IsReadOnly
    ) {
        Fail 'target-identity-changed-before-clean'
    }
    if ($protected.ContainsKey(([string]$live.SerialNumber).Trim())) {
        Fail 'target-became-protected-before-clean'
    }

    $diskpartScript = New-TemporaryFile
    try {
        @(
            "select disk $diskNumber"
            'clean'
            'exit'
        ) | Set-Content -LiteralPath $diskpartScript.FullName -Encoding ASCII
        $diskpartOutput = @(& diskpart.exe /s $diskpartScript.FullName 2>&1)
        $diskpartExit = $LASTEXITCODE
    } finally {
        Remove-Item -LiteralPath $diskpartScript.FullName -Force -ErrorAction SilentlyContinue
    }
    if ($diskpartExit -ne 0) {
        Fail "diskpart-clean-failed exit=$diskpartExit output=$($diskpartOutput -join ' | ')"
    }

    $refresh = Get-Command Update-HostStorageCache -ErrorAction SilentlyContinue
    if ($refresh) { Update-HostStorageCache }
    Start-Sleep -Seconds 2
    $live = Get-Disk -Number $diskNumber -ErrorAction Stop
    $remainingPartitions = @(Get-Partition -DiskNumber $diskNumber -ErrorAction SilentlyContinue)
    if (
        ([string]$live.SerialNumber).Trim() -ne $serial -or
        [int64]$live.Size -ne $expectedSize -or
        $live.BusType -ne 'USB' -or
        [bool]$live.IsBoot -or
        [bool]$live.IsSystem -or
        [bool]$live.IsReadOnly -or
        $remainingPartitions.Count -ne 0
    ) {
        Fail "removable-clean-not-proven partitions=$($remainingPartitions.Count)"
    }
    if ($protected.ContainsKey(([string]$live.SerialNumber).Trim())) {
        Fail 'target-became-protected-after-clean'
    }
    Write-Host "AURUM_TINYSEED_FLASH_PREP mode=removable-clean disk=$diskNumber serial=$serial partitions=0"
}

# Re-prove identity again immediately before opening the raw device.
$live = Get-Disk -Number $diskNumber -ErrorAction Stop
if (
    ([string]$live.SerialNumber).Trim() -ne $serial -or
    [int64]$live.Size -ne $expectedSize -or
    $live.BusType -ne 'USB' -or
    [bool]$live.IsBoot -or
    [bool]$live.IsSystem -or
    [bool]$live.IsReadOnly
) {
    Fail 'target-identity-changed-before-raw-write'
}
if ($protected.ContainsKey(([string]$live.SerialNumber).Trim())) {
    Fail 'target-became-protected-before-raw-write'
}

$bufferSize = 4MB
$buffer = New-Object byte[] $bufferSize
$source = [IO.File]::Open($image.FullName, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
try {
    $target = New-Object IO.FileStream(
        $physicalPath,
        [IO.FileMode]::Open,
        [IO.FileAccess]::ReadWrite,
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
