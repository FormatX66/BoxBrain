#Requires -Version 5.1
[CmdletBinding()]
param(
    [string[]]$PiAddresses = @("10.12.194.1", "10.42.194.1", "192.168.0.194"),
    [switch]$SkipDialogue
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$git = (Get-Command git.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
& $git -C $root checkout main
if ($LASTEXITCODE -ne 0) { throw "Could not select BoxBrain main." }
& $git -C $root pull --ff-only
if ($LASTEXITCODE -ne 0) { throw "Could not refresh BoxBrain main." }

# Morri is physically attached to BBPI4 over USB SSH. Prefer the verified USB
# gadget address first, then retain the AP and LAN routes as bounded fallbacks.
Write-Host "AURUM_ROUTE USB-SSH first: kali@$($PiAddresses[0])"

$reconciler = Join-Path $root "installer\reconcile-existing-aurum-gold-seed-on-pi.ps1"
& $reconciler -PiAddresses $PiAddresses

Write-Host "AURUM_GOLD_SEED_RECONCILED - existing Pi state and approved runtime persistence were preserved."

if (-not $SkipDialogue.IsPresent) {
    if ([string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) {
        Write-Host "AURUM_DIALOGUE_READY - OPENAI_API_KEY is not present in this process, so no live model session was started."
    }
    else {
        $question = "Do you prefer he, she, or they pronouns? You may also say that you have no preference or choose another form if that fits you better."
        $ask = Join-Path $root "installer\ask-aurum-on-pi.ps1"
        & $ask -Prompt $question -PiAddresses $PiAddresses
    }
}
