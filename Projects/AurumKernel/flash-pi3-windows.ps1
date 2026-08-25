[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$IntentPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Resolve-NormalizedPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    return [System.IO.Path]::GetFullPath($Path)
}

$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Pi 3 flashing requires an elevated Administrator process.'
}

$intentFile = Get-Item -LiteralPath $IntentPath
$intent = Get-Content -Raw -LiteralPath $intentFile.FullName | ConvertFrom-Json
if ($intent.schema -ne 'aurum-pi3-flash-intent-v2') {
    throw 'Flash intent schema mismatch.'
}

$diskNumber = [int]$intent.target.disk_number
if ($diskNumber -lt 1) {
    throw "Refusing unsafe disk number: $diskNumber"
}
$expectedDevice = "\\.\PhysicalDrive$diskNumber"
if ($intent.target.device_id -ne $expectedDevice) {
    throw 'Flash intent device path does not match its disk number.'
}

$disk = Get-Disk -Number $diskNumber
$drive = Get-CimInstance Win32_DiskDrive -Filter "Index=$diskNumber"
if ($disk.IsBoot -or $disk.IsSystem) {
    throw "Refusing Windows boot/system disk $diskNumber."
}
if ($disk.BusType -ne 'USB' -or $drive.MediaType -ne 'Removable Media') {
    throw "Refusing non-removable/non-USB disk $diskNumber."
}
if ($disk.IsReadOnly) {
    throw "Refusing read-only disk $diskNumber."
}
if ($disk.Size -ne [long]$intent.target.disk_bytes) {
    throw "Disk $diskNumber size changed after authorization."
}
if ($drive.DeviceID -ne $expectedDevice -or
    $drive.Model -ne $intent.target.model -or
    $drive.PNPDeviceID -ne $intent.target.pnp_device_id) {
    throw "Disk $diskNumber identity changed after authorization."
}

$prewriteKind = [string]$intent.target.prewrite_evidence.kind
if ($prewriteKind -eq 'boot-marker') {
    $bootPartition = Get-Partition -DiskNumber $diskNumber |
        Where-Object { $_.DriveLetter } |
        Select-Object -First 1
    if (-not $bootPartition) {
        throw "Disk $diskNumber no longer exposes the inspected boot partition."
    }
    $cmdlinePath = "$($bootPartition.DriveLetter):\cmdline.txt"
    if (-not (Test-Path -LiteralPath $cmdlinePath)) {
        throw 'The inspected Aurum boot cmdline marker is missing.'
    }
    $oldCmdline = Get-Content -Raw -LiteralPath $cmdlinePath
    if ($oldCmdline -notmatch [regex]::Escape([string]$intent.target.prewrite_evidence.marker)) {
        throw 'The inserted card no longer matches the authorized Aurum card.'
    }
}
elseif ($prewriteKind -eq 'prefix-sha256') {
    $prefixBytes = [int]$intent.target.prewrite_evidence.bytes
    if ($prefixBytes -lt 512 -or $prefixBytes -gt 67108864) {
        throw 'Unsafe pre-write prefix evidence length.'
    }
    $prefix = [byte[]]::new($prefixBytes)
    $prefixSource = [System.IO.FileStream]::new(
        $expectedDevice,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::ReadWrite,
        1048576,
        [System.IO.FileOptions]::SequentialScan
    )
    try {
        $prefixOffset = 0
        while ($prefixOffset -lt $prefixBytes) {
            $prefixRead = $prefixSource.Read($prefix, $prefixOffset, $prefixBytes - $prefixOffset)
            if ($prefixRead -eq 0) { throw 'Unexpected end of card during pre-write identity check.' }
            $prefixOffset += $prefixRead
        }
    }
    finally {
        $prefixSource.Dispose()
    }
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $prefixHash = [BitConverter]::ToString($sha256.ComputeHash($prefix)).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $sha256.Dispose()
    }
    if ($prefixHash -ne ([string]$intent.target.prewrite_evidence.sha256).ToLowerInvariant()) {
        throw 'Physical-card prefix changed after failed-write diagnosis.'
    }
}
else {
    throw "Unsupported pre-write evidence kind: $prewriteKind"
}

$image = Get-Item -LiteralPath ([string]$intent.source.path)
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $image.FullName).Hash.ToLowerInvariant()
$compressedHash = ([string]$intent.source.compressed_sha256).ToLowerInvariant()
$rawHash = ([string]$intent.source.raw_sha256).ToLowerInvariant()
if ($actualHash -ne $compressedHash) {
    throw 'Pi 3 image checksum mismatch inside the elevated flash process.'
}
if ($image.Length -ne [long]$intent.source.compressed_bytes) {
    throw 'Pi 3 image size changed inside the elevated flash process.'
}

$imager = 'C:\Program Files\Raspberry Pi Ltd\Imager\rpi-imager.exe'
if (-not (Test-Path -LiteralPath $imager)) {
    throw 'Raspberry Pi Imager is not installed at the expected path.'
}
$consoleLog = Resolve-NormalizedPath ([string]$intent.evidence.console_log)
$debugLog = Resolve-NormalizedPath ([string]$intent.evidence.debug_log)
$receiptPath = Resolve-NormalizedPath ([string]$intent.evidence.receipt)

Write-Output "AURUM_FLASH_START disk=$diskNumber device=$expectedDevice bytes=$($disk.Size)"
Write-Output "AURUM_FLASH_IMAGE path=$($image.FullName) compressed_sha256=$actualHash raw_sha256=$rawHash bytes=$($image.Length)"

[System.IO.File]::WriteAllText($consoleLog, '')
& $imager --cli --disable-eject --sha256 $rawHash --log-file $debugLog `
    $image.FullName $expectedDevice 2>&1 | Tee-Object -FilePath $consoleLog
$imagerExit = $LASTEXITCODE
if ($imagerExit -ne 0) {
    throw "Raspberry Pi Imager failed with exit code $imagerExit."
}

Update-HostStorageCache
Start-Sleep -Seconds 2
$partitions = @(Get-Partition -DiskNumber $diskNumber -ErrorAction SilentlyContinue |
    Sort-Object PartitionNumber |
    ForEach-Object {
        [ordered]@{
            number = $_.PartitionNumber
            drive_letter = if ($_.DriveLetter) { [string]$_.DriveLetter } else { $null }
            type = $_.Type
            bytes = [long]$_.Size
        }
    })

$receipt = [ordered]@{
    schema = 'aurum-pi3-flash-receipt-v1'
    state = 'success'
    carrier = 'Raspberry Pi Imager CLI'
    imager_version = (Get-Item -LiteralPath $imager).VersionInfo.ProductVersion
    imager_exit_code = $imagerExit
    imager_verification_enabled = $true
    source = [ordered]@{
        path = $image.FullName
        compressed_sha256 = $actualHash
        raw_sha256 = $rawHash
        compressed_bytes = [long]$image.Length
    }
    target = [ordered]@{
        disk_number = $diskNumber
        device_id = $expectedDevice
        model = $drive.Model
        pnp_device_id = $drive.PNPDeviceID
        disk_bytes = [long]$disk.Size
    }
    resulting_partitions = $partitions
    physical_pi3_boot = $false
}
$receipt | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 -LiteralPath $receiptPath
Write-Output "AURUM_FLASH_SUCCESS receipt=$receiptPath"
