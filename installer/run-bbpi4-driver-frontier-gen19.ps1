#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$OutputDirectory = 'evidence',
    [string]$RunTag = $env:GITHUB_RUN_ID
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$basePath = Join-Path $PSScriptRoot 'run-bbpi4-driver-frontier.ps1'
$extensionPath = Join-Path $PSScriptRoot 'aurum-pi4-driver-gen19-extension.ps1'
$frontierPath = Join-Path $repoRoot 'Projects\Codelation\driver_evidence\pi4_driver_frontier.json'
$evidencePath = Join-Path $repoRoot 'Projects\Codelation\driver_evidence\pi4_driver_gen18_verified.json'
foreach ($path in @($basePath, $extensionPath, $frontierPath, $evidencePath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing Aurum Pi4 generation-19 prerequisite: $path"
    }
}

$verified = Get-Content -LiteralPath $evidencePath -Raw | ConvertFrom-Json
if ($verified.schema -ne 'aurum-pi4-driver-generation-evidence-v1' -or [int]$verified.generation -ne 18) {
    throw 'Generation-19 requires committed generation-18 physical evidence.'
}
if ($verified.target -ne 'gpio-leds' -or $verified.device_class -ne 'noncritical-indicator' -or $verified.candidate_driver -ne 'aurum-gpio-leds') {
    throw 'Generation-18 evidence does not match the approved noncritical gpio-leds lane.'
}
$requiredTrue = @(
    'compile',
    'candidate_bind',
    'behavior_parity',
    'physical_default_trigger_parity',
    'physical_max_brightness_parity',
    'first_cycle_rollback',
    'first_cycle_candidate_module_unloaded',
    'ring_buffer_overlap_verified',
    'second_cycle_candidate_bind',
    'second_cycle_led_class_parity',
    'second_cycle_rollback',
    'second_cycle_candidate_module_unloaded',
    'third_cycle_candidate_bind',
    'third_cycle_led_class_parity',
    'third_cycle_rollback',
    'third_cycle_candidate_module_unloaded',
    'fourth_cycle_candidate_bind',
    'fourth_cycle_led_class_parity',
    'fourth_cycle_rollback',
    'fourth_cycle_candidate_module_unloaded'
)
foreach ($name in $requiredTrue) {
    if (-not [bool]$verified.verified.$name) {
        throw "Generation-18 evidence is missing required verified gate: $name"
    }
}
if ([int]$verified.verified.first_cycle_kernel_fault_signatures -ne 0 -or [int]$verified.verified.second_cycle_kernel_fault_signatures -ne 0 -or [int]$verified.verified.stress_kernel_fault_signatures -ne 0) {
    throw 'Generation-18 evidence contains a kernel-fault signature.'
}
if ([int]$verified.verified.cycles_without_reboot -lt 4) {
    throw 'Generation-18 evidence does not prove four cycles without reboot.'
}
foreach ($name in @('raw_mmio','firmware_changes','network_changes','storage_changes','persistent_boot_time_replacement')) {
    if ([bool]$verified.verified.$name) {
        throw "Generation-18 evidence crossed a prohibited boundary: $name"
    }
}

$original = [IO.File]::ReadAllText($basePath)
$patched = $original
$originalFrontier = [IO.File]::ReadAllText($frontierPath)
$newline = if ($original.Contains("`r`n")) { "`r`n" } else { "`n" }

$limitOld = 'elseif ($generation -eq $validated -and $next -eq ($validated + 1) -and $next -le 10) {'
$limitNew = 'elseif ($generation -eq $validated -and $next -eq ($validated + 1) -and $next -le 19) {'
if (-not $patched.Contains($limitOld)) {
    throw 'Could not extend the Aurum Pi4 autonomous next-generation limit to generation 19.'
}
$patched = $patched.Replace($limitOld, $limitNew)

$guardOld = 'if ($trialGeneration -lt 1 -or $trialGeneration -gt 10) {'
$guardNew = 'if ($trialGeneration -lt 1 -or $trialGeneration -gt 19) {'
if (-not $patched.Contains($guardOld)) {
    throw 'Could not extend the Aurum Pi4 supported-generation guard to generation 19.'
}
$patched = $patched.Replace($guardOld, $guardNew)

$marker = 'try {' + $newline + '    [IO.File]::WriteAllText($trialPath, $controlledTrial, [Text.UTF8Encoding]::new($false))'
$injected = ". '$extensionPath'" + $newline + $newline + $marker
if (-not $patched.Contains($marker)) {
    throw 'Could not locate the Aurum Pi4 generator-extension insertion point.'
}
$patched = $patched.Replace($marker, $injected)

$frontier = $originalFrontier | ConvertFrom-Json
if ([int]$frontier.validated_generation -gt 18) {
    throw "Committed frontier unexpectedly exceeds generation 18: $($frontier.validated_generation)"
}
$frontier.active_generation = 18
$frontier.validated_generation = 18
$frontier.next_generation = 19
$frontier.validated_capability = [string]$verified.capability
$controlledFrontier = $frontier | ConvertTo-Json -Depth 32

try {
    [IO.File]::WriteAllText($frontierPath, $controlledFrontier + $newline, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($basePath, $patched, [Text.UTF8Encoding]::new($false))
    Write-Host 'AURUM_PI4_DRIVER_GEN19_PREREQUISITE generation18=verified four_cycles=true kernel_fault_signatures=0 forbidden_boundaries=false'
    & $basePath -OutputDirectory $OutputDirectory -RunTag $RunTag
}
finally {
    [IO.File]::WriteAllText($basePath, $original, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($frontierPath, $originalFrontier, [Text.UTF8Encoding]::new($false))
}
