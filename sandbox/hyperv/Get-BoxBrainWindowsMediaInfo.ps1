[CmdletBinding()]
param(
    [string]$IsoPath = 'C:\VMs\BoxBrain-Windows-Lab\media\Windows11EnterpriseEval-25H2-en-us.iso',
    [string]$OutputPath = 'C:\VMs\BoxBrain-Windows-Lab\media-info.json'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated Windows PowerShell session.'
}

$IsoPath = [IO.Path]::GetFullPath($IsoPath)
if (-not (Test-Path -LiteralPath $IsoPath -PathType Leaf)) {
    throw "Windows installation media is missing: $IsoPath"
}

$diskImage = Mount-DiskImage -ImagePath $IsoPath -PassThru
try {
    $volume = $diskImage | Get-Volume
    if ([string]::IsNullOrWhiteSpace($volume.DriveLetter)) {
        throw 'The mounted Windows ISO has no drive letter.'
    }
    $sourcesRoot = "$($volume.DriveLetter):\sources"
    $imagePath = @(
        Join-Path $sourcesRoot 'install.wim'
        Join-Path $sourcesRoot 'install.esd'
    ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
        Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($imagePath)) {
        throw 'The Windows ISO contains neither sources\install.wim nor sources\install.esd.'
    }

    $images = @(
        Get-WindowsImage -ImagePath $imagePath |
            Select-Object ImageIndex, ImageName, Architecture, Version
    )
    if ($images.Count -eq 0) {
        throw 'No Windows images were found in the installation media.'
    }

    $result = [ordered]@{
        inspected_at = (Get-Date).ToUniversalTime().ToString('o')
        iso_path = $IsoPath
        iso_sha256 = (Get-FileHash -LiteralPath $IsoPath -Algorithm SHA256).Hash.ToLowerInvariant()
        image_container = Split-Path -Leaf $imagePath
        images = $images
    }
    $resultJson = $result | ConvertTo-Json -Depth 5
    $resultJson | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    $resultJson
} finally {
    Dismount-DiskImage -ImagePath $IsoPath | Out-Null
}
