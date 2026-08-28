[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$HopperAddress,

    [string]$IdentityFile = (Join-Path $env:USERPROFILE '.ssh\aurum_hopper_ed25519'),

    [string]$KnownHostsFile = (Join-Path $env:USERPROFILE '.ssh\aurum_hopper_known_hosts')
)

$ErrorActionPreference = 'Stop'
foreach ($path in @($IdentityFile, $KnownHostsFile)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required Hopper trust file is missing: $path" }
}
$ssh = (Get-Command ssh.exe -ErrorAction Stop).Source
& $ssh `
    -T `
    -i $IdentityFile `
    -o BatchMode=yes `
    -o IdentitiesOnly=yes `
    -o StrictHostKeyChecking=yes `
    -o "UserKnownHostsFile=$KnownHostsFile" `
    "aurum-remote@$HopperAddress" `
    seed-sync
if ($LASTEXITCODE -ne 0) { throw 'Hopper refused or failed the bounded seed-sync command.' }
