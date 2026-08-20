#Requires -Version 5.1
[CmdletBinding()]
param(
    [string[]]$Candidates = @(
        "10.12.194.1",   # preferred USB-C SSH route from the main Windows host
        "bbpi4.local",   # mDNS fallback
        "bbpi4",         # local DNS/NetBIOS-style fallback
        "10.42.194.1",   # alternate bounded USB/AP route
        "192.168.0.194"  # historical LAN fallback
    ),
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "Dedicated BBPI4 SSH key not found: $KeyPath"
}

$ssh = Get-Command ssh.exe -CommandType Application -ErrorAction Stop
$options = @(
    "-i", $KeyPath,
    "-o", "BatchMode=yes",
    "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "ConnectTimeout=3"
)

$attempts = @()
$selected = $null
$identity = $null

foreach ($candidate in $Candidates) {
    $output = @(& $ssh.Source @options "$PiUser@$candidate" "printf 'hostname='; hostname; printf 'arch='; uname -m; printf 'model='; tr -d '\000' </proc/device-tree/model 2>/dev/null || true; echo; test -d /opt/boxbrain/codelation -o -d /opt/aurum" 2>&1)
    $exit = $LASTEXITCODE
    $attempts += [ordered]@{
        candidate = $candidate
        reachable = ($exit -eq 0)
        exit = $exit
        detail = (($output -join "`n") | Select-Object -First 1)
    }
    if ($exit -eq 0) {
        $selected = $candidate
        $identity = ($output -join "`n")
        break
    }
}

$result = [ordered]@{
    schema = "bbpi4-route-v1"
    selected = $selected
    preferred_usb_route = "10.12.194.1"
    user = $PiUser
    identity = $identity
    attempts = $attempts
}

$result | ConvertTo-Json -Depth 6

if (-not $selected) {
    exit 2
}
