#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$OutputDirectory = 'evidence',
    [string]$RunTag = $env:GITHUB_RUN_ID
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontierPath = Join-Path $repoRoot 'Projects\Codelation\driver_evidence\pi4_driver_frontier.json'
$trialPath = Join-Path $repoRoot 'Projects\Codelation\run_pi4_single_driver_trial.sh'
$runnerPath = Join-Path $PSScriptRoot 'run-bbpi4-single-driver-trial.ps1'

foreach ($path in @($frontierPath, $trialPath, $runnerPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required Aurum Pi4 driver control file is missing: $path"
    }
}

$frontier = Get-Content -LiteralPath $frontierPath -Raw | ConvertFrom-Json
if ($frontier.schema -ne 'aurum-pi4-driver-frontier-v1') {
    throw "Unsupported Pi4 driver frontier schema: $($frontier.schema)"
}
if ($frontier.control_mode -ne 'git-build-channel-autonomous') {
    throw "Pi4 driver frontier is not in the approved autonomous build-channel mode."
}
if ($frontier.target -ne 'gpio-leds' -or $frontier.device_class -ne 'noncritical-indicator') {
    throw "Pi4 driver frontier requested an unapproved target or device class."
}
if ([bool]$frontier.operator_approval.required_per_iteration) {
    throw "Pi4 driver frontier currently requires operator approval per iteration."
}

$generation = [int]$frontier.active_generation
$validated = [int]$frontier.validated_generation
if ($generation -lt 1 -or $generation -gt $validated) {
    throw "Active generation $generation is outside the validated frontier $validated."
}

$trialGeneration = $generation
if ($frontier.PSObject.Properties.Name -contains 'trial_generation') {
    $trialGeneration = [int]$frontier.trial_generation
}
if ($trialGeneration -ne $generation) {
    $next = [int]$frontier.next_generation
    if ($trialGeneration -ne $next -or $trialGeneration -ne ($validated + 1)) {
        throw "Trial generation $trialGeneration must be exactly the next unvalidated generation after $validated."
    }
}
if ($trialGeneration -lt 1 -or $trialGeneration -gt 3) {
    throw "Trial generation $trialGeneration is unsupported by the bounded Pi4 build channel."
}

$requiredGates = @(
    'approved-bbpi4-strict-ssh-trust',
    'exact-raspberry-pi-4-model-check',
    'persistent-working-driver-backup-before-unbind',
    'candidate-compiles-before-any-live-swap',
    'automatic-restore-on-failure',
    'working-driver-rebound-before-success'
)
$declaredGates = @($frontier.required_gates)
foreach ($gate in $requiredGates) {
    if ($declaredGates -notcontains $gate) {
        throw "Pi4 driver frontier removed required safety gate: $gate"
    }
}

$original = [IO.File]::ReadAllText($trialPath)
$normalized = $original.Replace("`r`n", "`n").Replace("`r", "`n")
$pattern = 'GENERATION="\$\{AURUM_DRIVER_GENERATION:-\d+\}"'
$replacement = 'GENERATION="${AURUM_DRIVER_GENERATION:-' + $trialGeneration + '}"'
$controlled = [regex]::Replace($normalized, $pattern, $replacement, 1)
if ($controlled -eq $normalized -and $normalized -notmatch [regex]::Escape($replacement)) {
    throw 'Could not bind the Pi4 trial script to the requested generation in the Git frontier.'
}

if ($trialGeneration -eq 3) {
    $generationGate = '[[ "$GENERATION" == "1" || "$GENERATION" == "2" ]]'
    $generationGate3 = '[[ "$GENERATION" == "1" || "$GENERATION" == "2" || "$GENERATION" == "3" ]]'
    if (-not $controlled.Contains($generationGate)) {
        throw 'Could not extend the bounded Pi4 trial generation gate for generation 3.'
    }
    $controlled = $controlled.Replace($generationGate, $generationGate3)

    $parityGate = 'if [[ "$GENERATION" == "2" ]]; then'
    if (-not $controlled.Contains($parityGate)) {
        throw 'Could not extend the Pi4 behavior-parity gate for generation 3.'
    }
    $controlled = $controlled.Replace($parityGate, 'if [[ "$GENERATION" == "2" || "$GENERATION" == "3" ]]; then')
}

try {
    [IO.File]::WriteAllText($trialPath, $controlled, [Text.UTF8Encoding]::new($false))
    Write-Host "AURUM_PI4_DRIVER_FRONTIER target=$($frontier.target) class=$($frontier.device_class) active_generation=$generation validated_generation=$validated trial_generation=$trialGeneration next_generation=$($frontier.next_generation) approval_per_iteration=false"
    & $runnerPath -OutputDirectory $OutputDirectory -RunTag $RunTag
    if ($LASTEXITCODE -ne 0) {
        throw "Pi4 driver frontier execution failed with exit code $LASTEXITCODE"
    }
}
finally {
    [IO.File]::WriteAllText($trialPath, $original, [Text.UTF8Encoding]::new($false))
}
