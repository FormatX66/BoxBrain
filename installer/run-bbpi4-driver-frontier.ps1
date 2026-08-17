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
$generatorPath = Join-Path $repoRoot 'Projects\Codelation\pi4_driver_synthesizer.py'
$runnerPath = Join-Path $PSScriptRoot 'run-bbpi4-single-driver-trial.ps1'

foreach ($path in @($frontierPath, $trialPath, $generatorPath, $runnerPath)) {
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

$next = [int]$frontier.next_generation
$trialGeneration = $generation
if ($frontier.PSObject.Properties.Name -contains 'trial_generation') {
    $trialGeneration = [int]$frontier.trial_generation
}
elseif ($generation -eq $validated -and $next -eq ($validated + 1) -and $next -le 9) {
    # The Git frontier explicitly permits autonomous iteration on the same bounded
    # noncritical target. Automatically exercise the next supported generation;
    # promotion still remains evidence-gated and is never done by this runner.
    $trialGeneration = $next
}
if ($trialGeneration -ne $generation) {
    if ($trialGeneration -ne $next -or $trialGeneration -ne ($validated + 1)) {
        throw "Trial generation $trialGeneration must be exactly the next unvalidated generation after $validated."
    }
}
if ($trialGeneration -lt 1 -or $trialGeneration -gt 9) {
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

$originalTrial = [IO.File]::ReadAllText($trialPath)
$normalizedTrial = $originalTrial.Replace("`r`n", "`n").Replace("`r", "`n")
$pattern = 'GENERATION="\$\{AURUM_DRIVER_GENERATION:-\d+\}"'
$replacement = 'GENERATION="${AURUM_DRIVER_GENERATION:-' + $trialGeneration + '}"'
$controlledTrial = [regex]::Replace($normalizedTrial, $pattern, $replacement, 1)
if ($controlledTrial -eq $normalizedTrial -and $normalizedTrial -notmatch [regex]::Escape($replacement)) {
    throw 'Could not bind the Pi4 trial script to the requested generation in the Git frontier.'
}

if ($trialGeneration -ge 3) {
    $generationGate = '[[ "$GENERATION" == "1" || "$GENERATION" == "2" ]]'
    $allowedGenerations = 1..$trialGeneration | ForEach-Object { '"' + $_ + '"' }
    $generationGateExpanded = '[[ ' + (($allowedGenerations | ForEach-Object { '"$GENERATION" == ' + $_ }) -join ' || ') + ' ]]'
    if (-not $controlledTrial.Contains($generationGate)) {
        throw "Could not extend the bounded Pi4 trial generation gate for generation $trialGeneration."
    }
    $controlledTrial = $controlledTrial.Replace($generationGate, $generationGateExpanded)

    $parityGate = 'if [[ "$GENERATION" == "2" ]]; then'
    $parityGenerations = 2..$trialGeneration | ForEach-Object { '"$GENERATION" == "' + $_ + '"' }
    $parityGateExpanded = 'if [[ ' + ($parityGenerations -join ' || ') + ' ]]; then'
    if (-not $controlledTrial.Contains($parityGate)) {
        throw "Could not extend the Pi4 behavior-parity gate for generation $trialGeneration."
    }
    $controlledTrial = $controlledTrial.Replace($parityGate, $parityGateExpanded)
}

$originalGenerator = [IO.File]::ReadAllText($generatorPath)
$controlledGenerator = $originalGenerator
if ($trialGeneration -ge 9) {
    $patches = @(
        [pscustomobject]@{
            Old = 'elif generation in {3, 4, 5, 6, 7, 8}:'
            New = 'elif generation in {3, 4, 5, 6, 7, 8, 9}:'
        },
        [pscustomobject]@{
            Old = '            8: "reference-aligned topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, firmware LED policy flags, default-state initialization, sleep-aware GPIO LED writes, and learned Pi readback semantics",'
            New = '            8: "reference-aligned topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, firmware LED policy flags, default-state initialization, sleep-aware GPIO LED writes, and learned Pi readback semantics",' + "`n" + '            9: "reference-aligned counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, firmware LED policy flags, default-state initialization, sleep-aware GPIO LED writes, and learned Pi readback semantics",'
        },
        [pscustomobject]@{
            Old = '    struct aurum_led leds[];'
            New = '    struct aurum_led leds[] __counted_by(count);'
        },
        [pscustomobject]@{
            Old = 'if generation not in {1, 2, 3, 4, 5, 6, 7, 8}:'
            New = 'if generation not in {1, 2, 3, 4, 5, 6, 7, 8, 9}:'
        },
        [pscustomobject]@{
            Old = '        8: "reference-aligned topology-sized overflow-safe LED allocation plus LED default pinctrl selection, GPIO consumer identity, firmware LED policy flags, default-state initialization, sleep-aware GPIO LED writes, and reference-compatible readback",'
            New = '        8: "reference-aligned topology-sized overflow-safe LED allocation plus LED default pinctrl selection, GPIO consumer identity, firmware LED policy flags, default-state initialization, sleep-aware GPIO LED writes, and reference-compatible readback",' + "`n" + '        9: "reference-aligned counted flexible-array metadata plus topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, firmware LED policy flags, default-state initialization, sleep-aware GPIO LED writes, and reference-compatible readback",'
        },
        [pscustomobject]@{
            Old = '        "topology_sized_overflow_safe_allocation": generation >= 8,'
            New = '        "topology_sized_overflow_safe_allocation": generation >= 8,' + "`n" + '        "counted_flexible_array_metadata": generation >= 9,'
        }
    )
    foreach ($patch in $patches) {
        if (-not $controlledGenerator.Contains($patch.Old)) {
            throw "Could not apply bounded generation-9 synthesizer patch: $($patch.Old)"
        }
        $controlledGenerator = $controlledGenerator.Replace($patch.Old, $patch.New)
    }
}

try {
    [IO.File]::WriteAllText($trialPath, $controlledTrial, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($generatorPath, $controlledGenerator, [Text.UTF8Encoding]::new($false))
    Write-Host "AURUM_PI4_DRIVER_FRONTIER target=$($frontier.target) class=$($frontier.device_class) active_generation=$generation validated_generation=$validated trial_generation=$trialGeneration next_generation=$next approval_per_iteration=false"
    if ($trialGeneration -ge 9) {
        Write-Host "AURUM_PI4_DRIVER_GEN9 reference=counted-flexible-array-metadata source=raspberrypi-linux-rpi-6.12.y bounded=true"
    }
    & $runnerPath -OutputDirectory $OutputDirectory -RunTag $RunTag
    if ($LASTEXITCODE -ne 0) {
        throw "Pi4 driver frontier execution failed with exit code $LASTEXITCODE"
    }
}
finally {
    [IO.File]::WriteAllText($trialPath, $originalTrial, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($generatorPath, $originalGenerator, [Text.UTF8Encoding]::new($false))
}
