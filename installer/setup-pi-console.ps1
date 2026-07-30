#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$PiAddress = "10.12.194.1",
    [ValidatePattern("^[a-z_][a-z0-9_-]{0,31}$")]
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519"),
    [switch]$SkipShortcut
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-PrivateOrLinkLocalAddress {
    param([Parameter(Mandatory)][string]$Address)

    $parsed = $null
    if (-not [Net.IPAddress]::TryParse($Address, [ref]$parsed)) {
        return $false
    }
    $bytes = $parsed.GetAddressBytes()
    if ($bytes.Length -ne 4) {
        return $false
    }
    return (
        $bytes[0] -eq 10 -or
        ($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31) -or
        ($bytes[0] -eq 192 -and $bytes[1] -eq 168) -or
        ($bytes[0] -eq 169 -and $bytes[1] -eq 254)
    )
}

if (-not (Test-PrivateOrLinkLocalAddress -Address $PiAddress)) {
    throw "PiAddress must be a private or link-local IPv4 address."
}
if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "The BoxBrain SSH key was not found at $KeyPath."
}

$ssh = Get-Command ssh.exe -ErrorAction Stop
$scp = Get-Command scp.exe -ErrorAction Stop
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$scriptDirectory = Join-Path $repositoryRoot "edge\kali-pi-agent\scripts"
$sourceScripts = @(
    (Join-Path $scriptDirectory "install-console.sh"),
    (Join-Path $scriptDirectory "start-console.sh"),
    (Join-Path $scriptDirectory "stop-console.sh")
)
foreach ($sourceScript in $sourceScripts) {
    if (-not (Test-Path -LiteralPath $sourceScript -PathType Leaf)) {
        throw "Required Pi console source is missing: $sourceScript"
    }
}

$target = "$PiUser@$PiAddress"
$remoteRoot = "/tmp/boxbrain-console-$([Guid]::NewGuid().ToString('N'))"
$remoteScripts = "$remoteRoot/scripts"
$sshOptions = @(
    "-i", $KeyPath,
    "-o", "BatchMode=yes",
    "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "ConnectTimeout=8"
)
$cleanupCommand = (
    "rm -f -- '$remoteScripts/install-console.sh' " +
    "'$remoteScripts/start-console.sh' '$remoteScripts/stop-console.sh'; " +
    "rmdir -- '$remoteScripts' '$remoteRoot' 2>/dev/null || true"
)

try {
    & $ssh.Source @sshOptions $target `
        "umask 077; mkdir -p -- '$remoteScripts'"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the bounded temporary setup directory on the Pi."
    }

    & $scp.Source @sshOptions @sourceScripts "${target}:$remoteScripts/"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not copy the Pi console setup scripts."
    }

    & $ssh.Source @sshOptions $target `
        "sudo -n sh '$remoteScripts/install-console.sh'"
    if ($LASTEXITCODE -ne 0) {
        throw "The Pi console installer failed. No missing packages were installed automatically."
    }
}
finally {
    & $ssh.Source @sshOptions $target $cleanupCommand 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "The uniquely named Pi setup directory could not be removed."
    }
}

if (-not $SkipShortcut) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $shortcutPath = Join-Path $desktop "BoxBrain Pi Screen.lnk"
    if (Test-Path -LiteralPath $shortcutPath) {
        Write-Warning "The existing BoxBrain Pi Screen shortcut was preserved."
    }
    else {
        & (Join-Path $PSScriptRoot "install-pi-console-shortcut.ps1")
    }
}

Write-Output "Pi console setup completed. It remains stopped until the launcher is used."
