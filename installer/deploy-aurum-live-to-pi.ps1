#Requires -Version 5.1
[CmdletBinding()]
param(
    [string[]]$PiAddresses = @("10.12.194.1", "10.42.194.1", "192.168.0.194"),
    [string]$PiUser = "kali",
    [string]$KeyPath = (Join-Path $HOME ".ssh\boxbrain_pi_ed25519"),
    [string]$SshExecutable,
    [string]$ScpExecutable,
    [string]$UserKnownHostsFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# The BBPI4 gold seed is already installed. The live-graph deploy entry point now
# performs an in-place reconciliation: it preserves the opaque seed and existing
# approved runtime persistence, installs only the bounded dialogue/live-graph
# files, and rejects only newly introduced persistence. Morri currently reaches
# BBPI4 over USB SSH, so 10.12.194.1 is the first bounded route.
$reconciler = Join-Path $PSScriptRoot "reconcile-existing-aurum-gold-seed-on-pi.ps1"
if (-not (Test-Path -LiteralPath $reconciler -PathType Leaf)) {
    throw "The Aurum gold-seed reconciler is missing: $reconciler"
}

$arguments = @{
    PiAddresses = $PiAddresses
    PiUser = $PiUser
    KeyPath = $KeyPath
}
if ($SshExecutable) { $arguments.SshExecutable = $SshExecutable }
if ($ScpExecutable) { $arguments.ScpExecutable = $ScpExecutable }
if ($UserKnownHostsFile) { $arguments.UserKnownHostsFile = $UserKnownHostsFile }
& $reconciler @arguments
