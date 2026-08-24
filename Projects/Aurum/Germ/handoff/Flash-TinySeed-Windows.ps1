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

if (-not ('AurumTinySeedVolumeNative' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

public static class AurumTinySeedVolumeNative {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern SafeFileHandle CreateFile(
        string fileName,
        uint desiredAccess,
        uint shareMode,
        IntPtr securityAttributes,
        uint creationDisposition,
        uint flagsAndAttributes,
        IntPtr templateFile
    );

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool DeviceIoControl(
        SafeFileHandle device,
        uint controlCode,
        IntPtr inBuffer,
        uint inBufferSize,
        IntPtr outBuffer,
        uint outBufferSize,
        out uint bytesReturned,
        IntPtr overlapped
    );
}
'@
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
$expectedModel = [string]$disk.FriendlyName

function Get-ReverifiedTarget {
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        $usbDisks = @(Get-Disk -ErrorAction SilentlyContinue | Where-Object { $_.BusType -eq 'USB' })
        $liveMatches = @($usbDisks | Where-Object { ([string]$_.SerialNumber).Trim() -eq $serial })
        if ($usbDisks.Count -gt 1) { Fail "usb-selection-became-ambiguous count=$($usbDisks.Count)" }
        if ($liveMatches.Count -gt 1) { Fail "disk-serial-not-unique count=$($liveMatches.Count)" }
        if ($liveMatches.Count -eq 1 -and -not [bool]$liveMatches[0].IsOffline) { break }
        Start-Sleep -Seconds 2
    } while ([DateTime]::UtcNow -lt $deadline)

    if ($liveMatches.Count -ne 1) { Fail "target-not-present-after-io-reset count=$($liveMatches.Count)" }
    $candidate = $liveMatches[0]
    if ([bool]$candidate.IsOffline) { Fail 'target-remained-offline-after-io-reset' }
    if (
        [int64]$candidate.Size -ne $expectedSize -or
        [string]$candidate.FriendlyName -ne $expectedModel -or
        $candidate.BusType -ne 'USB' -or
        [bool]$candidate.IsBoot -or
        [bool]$candidate.IsSystem -or
        [bool]$candidate.IsReadOnly
    ) {
        Fail 'target-identity-changed-before-io'
    }
    if ($protected.ContainsKey(([string]$candidate.SerialNumber).Trim())) {
        Fail 'target-became-protected-before-io'
    }
    return $candidate
}

$script:targetVolumeLocks = New-Object System.Collections.ArrayList

function Release-TargetVolumeLocks {
    foreach ($handle in @($script:targetVolumeLocks)) {
        if ($null -ne $handle) { try { $handle.Dispose() } catch { } }
    }
    $script:targetVolumeLocks.Clear()
}

function Dismount-TargetVolumes([int]$Number) {
    Release-TargetVolumeLocks
    $letters = @(Get-Partition -DiskNumber $Number -ErrorAction SilentlyContinue |
        Where-Object { $_.DriveLetter } | ForEach-Object { [string]$_.DriveLetter })
    foreach ($letter in $letters) {
        & mountvol "$letter`:" /P | Out-Null
        if ($LASTEXITCODE -ne 0) { Fail "volume-dismount-failed drive=$letter" }
    }

    $volumePaths = @(Get-Partition -DiskNumber $Number -ErrorAction SilentlyContinue |
        ForEach-Object { @($_.AccessPaths) } |
        Where-Object { ([string]$_).StartsWith('\\?\Volume{') } |
        Sort-Object -Unique)
    foreach ($volumePathValue in $volumePaths) {
        $volumePath = [string]$volumePathValue
        if ($volumePath.EndsWith('\')) { $volumePath = $volumePath.Substring(0, $volumePath.Length - 1) }
        $handle = [AurumTinySeedVolumeNative]::CreateFile(
            $volumePath,
            [uint32]3221225472,
            [uint32]3,
            [IntPtr]::Zero,
            [uint32]3,
            [uint32]128,
            [IntPtr]::Zero
        )
        if ($handle.IsInvalid) {
            $code = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
            $handle.Dispose()
            Fail "volume-lock-open-failed path=$volumePath win32=$code"
        }
        [uint32]$bytesReturned = 0
        if (-not [AurumTinySeedVolumeNative]::DeviceIoControl(
            $handle, [uint32]0x00090018, [IntPtr]::Zero, 0,
            [IntPtr]::Zero, 0, [ref]$bytesReturned, [IntPtr]::Zero
        )) {
            $code = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
            $handle.Dispose()
            Fail "volume-lock-failed path=$volumePath win32=$code"
        }
        if (-not [AurumTinySeedVolumeNative]::DeviceIoControl(
            $handle, [uint32]0x00090020, [IntPtr]::Zero, 0,
            [IntPtr]::Zero, 0, [ref]$bytesReturned, [IntPtr]::Zero
        )) {
            $code = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
            $handle.Dispose()
            Fail "volume-dismount-ioctl-failed path=$volumePath win32=$code"
        }
        [void]$script:targetVolumeLocks.Add($handle)
        Write-Host "AURUM_TINYSEED_FLASH_VOLUME_LOCKED disk=$Number path=$volumePath"
    }
}

function Clear-ReverifiedTarget {
    Release-TargetVolumeLocks
    $candidate = Get-ReverifiedTarget
    $number = [int]$candidate.Number
    # Get-ReverifiedTarget is the immediate identity proof for this destructive
    # clear. Only the exact serial/model/size USB can reach this command.
    Clear-Disk -Number $number -RemoveData -RemoveOEM -Confirm:$false -ErrorAction Stop | Out-Null
    Update-HostStorageCache -ErrorAction SilentlyContinue | Out-Null
    Start-Sleep -Seconds 2
    $candidate = Get-ReverifiedTarget
    if ($candidate.PartitionStyle -ne 'RAW' -or [int]$candidate.NumberOfPartitions -ne 0) {
        Fail "target-clear-not-observed style=$($candidate.PartitionStyle) partitions=$($candidate.NumberOfPartitions)"
    }
}

function Test-ImageFirstSector([byte[]]$Expected) {
    $candidate = Get-ReverifiedTarget
    $path = "\\.\PhysicalDrive$([int]$candidate.Number)"
    $reader = $null
    try {
        $reader = New-Object IO.FileStream(
            $path,
            [IO.FileMode]::Open,
            [IO.FileAccess]::Read,
            [IO.FileShare]::ReadWrite,
            4096,
            [IO.FileOptions]::SequentialScan
        )
        $observed = New-Object byte[] 512
        $count = $reader.Read($observed, 0, $observed.Length)
        if ($count -ne $observed.Length) { return $false }
        for ($index = 0; $index -lt $observed.Length; $index += 1) {
            if ($observed[$index] -ne $Expected[$index]) { return $false }
        }
        return $true
    } catch [IO.IOException] {
        return $false
    } finally {
        if ($null -ne $reader) { try { $reader.Dispose() } catch { } }
    }
}

function Write-And-VerifyImageFirstSector {
    $imageReader = [IO.File]::Open($image.FullName, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try {
        $firstSector = New-Object byte[] 512
        if ($imageReader.Read($firstSector, 0, $firstSector.Length) -ne $firstSector.Length) {
            Fail 'image-first-sector-short-read'
        }
    } finally {
        $imageReader.Dispose()
    }

    for ($attempt = 1; $attempt -le 4; $attempt += 1) {
        Clear-ReverifiedTarget
        $candidate = Get-ReverifiedTarget
        $path = "\\.\PhysicalDrive$([int]$candidate.Number)"
        $writer = $null
        try {
            $writer = New-Object IO.FileStream(
                $path,
                [IO.FileMode]::Open,
                [IO.FileAccess]::Write,
                [IO.FileShare]::ReadWrite,
                4096,
                [IO.FileOptions]::WriteThrough
            )
            $writer.Write($firstSector, 0, $firstSector.Length)
            $writer.Flush($true)
        } catch [IO.IOException] {
            Write-Host "AURUM_TINYSEED_FLASH_IO_RETRY phase=first-sector attempt=$attempt"
        } finally {
            if ($null -ne $writer) { try { $writer.Dispose() } catch { } }
        }
        Start-Sleep -Seconds 3
        Update-HostStorageCache -ErrorAction SilentlyContinue | Out-Null
        if (Test-ImageFirstSector $firstSector) {
            Write-Host 'AURUM_TINYSEED_FLASH_FIRST_SECTOR_OK bytes=512'
            return
        }
    }
    Fail 'image-first-sector-write-retry-exhausted'
}

# Re-prove identity immediately before the first destructive operation. Keep
# removable media online: some USB firmware re-enumerates after sector zero
# changes and reports a transient ERROR_NOT_READY if Windows was asked to
# offline it. Every reopen below repeats the same physical identity proof.
$live = Get-ReverifiedTarget
$diskNumber = [int]$live.Number
$physicalPath = "\\.\PhysicalDrive$diskNumber"
Write-And-VerifyImageFirstSector
$live = Get-ReverifiedTarget
$diskNumber = [int]$live.Number
$physicalPath = "\\.\PhysicalDrive$diskNumber"
Dismount-TargetVolumes $diskNumber

$bufferSize = 4MB
$buffer = New-Object byte[] $bufferSize
$maxIoRetries = 8
$source = [IO.File]::Open($image.FullName, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
$target = $null
try {
    [int64]$written = 512
    [void]$source.Seek($written, [IO.SeekOrigin]::Begin)
    while (($read = $source.Read($buffer, 0, $buffer.Length)) -gt 0) {
        $attempt = 0
        while ($true) {
            try {
                if ($null -eq $target) {
                    $live = Get-ReverifiedTarget
                    $diskNumber = [int]$live.Number
                    Dismount-TargetVolumes $diskNumber
                    $physicalPath = "\\.\PhysicalDrive$diskNumber"
                    $target = New-Object IO.FileStream(
                        $physicalPath,
                        [IO.FileMode]::Open,
                        [IO.FileAccess]::Write,
                        [IO.FileShare]::ReadWrite,
                        $bufferSize,
                        [IO.FileOptions]::WriteThrough
                    )
                    [void]$target.Seek($written, [IO.SeekOrigin]::Begin)
                }
                $target.Write($buffer, 0, $read)
                $written += $read
                break
            } catch [IO.IOException] {
                if ($null -ne $target) {
                    try { $target.Dispose() } catch { }
                    $target = $null
                }
                $attempt += 1
                if ($attempt -gt $maxIoRetries) {
                    Fail "device-write-retry-exhausted offset=$written error=$($_.Exception.Message)"
                }
                Write-Host "AURUM_TINYSEED_FLASH_IO_RETRY phase=write offset=$written attempt=$attempt"
                Start-Sleep -Seconds 3
            }
        }
    }
    if ($null -ne $target) {
        try {
            $target.Flush($true)
        } catch [IO.IOException] {
            # WriteThrough was used for every block. A reset during the final
            # flush is resolved by the authoritative full raw readback below.
            Write-Host 'AURUM_TINYSEED_FLASH_IO_RETRY phase=final-flush action=verify-by-full-readback'
            Start-Sleep -Seconds 3
        }
    }
} finally {
    if ($null -ne $target) { try { $target.Dispose() } catch { } }
    $source.Dispose()
}

# Full image-length readback hash. This is deliberately slower than a spot check
# because READY_TO_BOOT should mean the bytes written were actually re-read.
$sha = [Security.Cryptography.SHA256]::Create()
$reader = $null
try {
    [int64]$verified = 0
    [int64]$remaining = [int64]$image.Length
    while ($remaining -gt 0) {
        $attempt = 0
        while ($true) {
            try {
                if ($null -eq $reader) {
                    $live = Get-ReverifiedTarget
                    $diskNumber = [int]$live.Number
                    Dismount-TargetVolumes $diskNumber
                    $physicalPath = "\\.\PhysicalDrive$diskNumber"
                    $reader = New-Object IO.FileStream(
                        $physicalPath,
                        [IO.FileMode]::Open,
                        [IO.FileAccess]::Read,
                        [IO.FileShare]::ReadWrite,
                        $bufferSize,
                        [IO.FileOptions]::SequentialScan
                    )
                    [void]$reader.Seek($verified, [IO.SeekOrigin]::Begin)
                }
                $want = [int][Math]::Min([int64]$buffer.Length, $remaining)
                $read = $reader.Read($buffer, 0, $want)
                if ($read -le 0) { Fail 'unexpected-end-of-device-during-readback' }
                [void]$sha.TransformBlock($buffer, 0, $read, $null, 0)
                $verified += $read
                $remaining -= $read
                break
            } catch [IO.IOException] {
                if ($null -ne $reader) {
                    try { $reader.Dispose() } catch { }
                    $reader = $null
                }
                $attempt += 1
                if ($attempt -gt $maxIoRetries) {
                    Fail "device-readback-retry-exhausted offset=$verified error=$($_.Exception.Message)"
                }
                Write-Host "AURUM_TINYSEED_FLASH_IO_RETRY phase=readback offset=$verified attempt=$attempt"
                Start-Sleep -Seconds 3
            }
        }
    }
    [void]$sha.TransformFinalBlock([byte[]]::new(0), 0, 0)
    $readback = ([BitConverter]::ToString($sha.Hash)).Replace('-', '').ToLowerInvariant()
} finally {
    if ($null -ne $reader) { try { $reader.Dispose() } catch { } }
    $sha.Dispose()
}

Release-TargetVolumeLocks
if ($readback -ne $actual) { Fail "raw-readback-mismatch actual=$readback expected=$actual" }
Write-Host "AURUM_TINYSEED_FLASH_OK disk=$diskNumber serial=$serial image_sha256=$actual raw_readback_verified=true"
