#Requires -Version 5.1
[CmdletBinding()]
param(
    [string[]]$PiAddresses = @("10.42.194.1", "10.12.194.1", "192.168.0.194"),
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "The dedicated BoxBrain SSH identity was not found at $KeyPath."
}

$ssh = Get-Command ssh.exe -ErrorAction Stop
$scp = Get-Command scp.exe -ErrorAction Stop
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$source = Join-Path $repositoryRoot "Projects\Codelation"
if (-not (Test-Path -LiteralPath $source -PathType Container)) {
    throw "Codelation source is missing: $source"
}

$options = @(
    "-i", $KeyPath,
    "-o", "BatchMode=yes",
    "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "ConnectTimeout=4"
)

$selected = $null
foreach ($address in $PiAddresses) {
    & $ssh.Source @options "$PiUser@$address" "true" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $selected = $address
        break
    }
}
if ($null -eq $selected) {
    throw "BBPI4 was not reachable over the AP, USB-C, or LAN SSH routes."
}

$target = "$PiUser@$selected"
$transfer = "/tmp/codelation-$([Guid]::NewGuid().ToString('N'))"
$cleanup = "rm -rf -- '$transfer'"
try {
    & $ssh.Source @options $target "umask 077; mkdir -p -- '$transfer'"
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Pi transfer directory." }

    & $scp.Source @options -r "$source\*" "${target}:$transfer/"
    if ($LASTEXITCODE -ne 0) { throw "Codelation transfer failed." }

    $install = @"
set -eu
cd '$transfer'
python3 -m unittest discover -s tests -v
sudo -n install -d -o '$PiUser' -g '$PiUser' /opt/boxbrain/codelation
sudo -n cp -a . /opt/boxbrain/codelation/
sudo -n chown -R '${PiUser}:${PiUser}' /opt/boxbrain/codelation
cd /opt/boxbrain/codelation
python3 seed/codelation_seed.py summary --model seed.bin
python3 --version
"@
    & $ssh.Source @options $target $install
    if ($LASTEXITCODE -ne 0) { throw "Codelation verification or installation failed." }
}
finally {
    & $ssh.Source @options $target $cleanup 2>$null
}

Write-Output "CODELATION_DEPLOYED address=$selected path=/opt/boxbrain/codelation"
