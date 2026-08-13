#Requires -Version 5.1
[CmdletBinding()]
param(
    [string[]]$PiAddresses = @("10.42.194.1", "10.12.194.1", "192.168.0.194"),
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# The BBPI4 gold seed is already installed. The live-graph deploy entry point now
# performs an in-place reconciliation: it preserves the opaque seed and existing
# approved runtime persistence, installs only the bounded dialogue/live-graph
# files, and rejects only newly introduced persistence.
$reconciler = Join-Path $PSScriptRoot "reconcile-existing-aurum-gold-seed-on-pi.ps1"
if (-not (Test-Path -LiteralPath $reconciler -PathType Leaf)) {
    throw "The Aurum gold-seed reconciler is missing: $reconciler"
}

$arguments = @{
    PiAddresses = $PiAddresses
    PiUser = $PiUser
    KeyPath = $KeyPath
}
& $reconciler @arguments
