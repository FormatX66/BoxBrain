#Requires -Version 5.1
[CmdletBinding()]
param(
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

$reconciler = Join-Path $root "installer\reconcile-existing-aurum-gold-seed-on-pi.ps1"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $reconciler
if ($LASTEXITCODE -ne 0) { throw "Existing BBPI4 Aurum gold-seed reconciliation failed." }

Write-Host "AURUM_GOLD_SEED_RECONCILED - existing Pi state and approved runtime persistence were preserved."

if (-not $SkipDialogue.IsPresent) {
    if ([string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) {
        Write-Host "AURUM_DIALOGUE_READY - OPENAI_API_KEY is not present in this process, so no live model session was started."
    }
    else {
        $question = "Do you prefer he, she, or they pronouns? You may also say that you have no preference or choose another form if that fits you better."
        $ask = Join-Path $root "installer\ask-aurum-on-pi.ps1"
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ask -Prompt $question
        if ($LASTEXITCODE -ne 0) { throw "Aurum dialogue/self-build session failed after gold-seed reconciliation." }
    }
}
