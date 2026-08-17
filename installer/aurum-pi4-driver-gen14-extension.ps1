#Requires -Version 5.1
Set-StrictMode -Version Latest

$gen13Extension = Join-Path $PSScriptRoot 'aurum-pi4-driver-gen13-extension.ps1'
if (-not (Test-Path -LiteralPath $gen13Extension -PathType Leaf)) {
    throw "Missing Aurum Pi4 generation-13 extension: $gen13Extension"
}
. $gen13Extension

if ($trialGeneration -ge 14) {
    $generation14Patches = @(
        [pscustomobject]@{
            Old = 'elif generation in {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13}:'
            New = 'elif generation in {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14}:'
        },
        [pscustomobject]@{
            Old = '            13: "reference-aligned LED-core firmware policy delegation with physical default-trigger parity, shutdown LED policy, GPIO direction-flag handling, unified LED setter dispatch, counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, default-state initialization, sleep-aware GPIO LED writes, and learned Pi readback semantics",'
            New = '            13: "reference-aligned LED-core firmware policy delegation with physical default-trigger parity, shutdown LED policy, GPIO direction-flag handling, unified LED setter dispatch, counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, default-state initialization, sleep-aware GPIO LED writes, and learned Pi readback semantics",' + "`n" + '            14: "physical LED-class max-brightness and default-trigger parity closure over the reference-aligned LED-core firmware policy path, shutdown LED policy, GPIO direction handling, topology-safe allocation, pinctrl, identity, default-state initialization, sleep-aware GPIO writes, and readback semantics",'
        },
        [pscustomobject]@{
            Old = 'if generation not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13}:'
            New = 'if generation not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14}:'
        },
        [pscustomobject]@{
            Old = '        13: "reference-aligned LED-core firmware policy delegation with physical default-trigger parity plus shutdown LED policy, GPIO direction-flag handling, unified LED setter dispatch, counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, default-state initialization, sleep-aware GPIO LED writes, and reference-compatible readback",'
            New = '        13: "reference-aligned LED-core firmware policy delegation with physical default-trigger parity plus shutdown LED policy, GPIO direction-flag handling, unified LED setter dispatch, counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, default-state initialization, sleep-aware GPIO LED writes, and reference-compatible readback",' + "`n" + '        14: "physical LED-class max-brightness and default-trigger parity closure over the reference-aligned LED-core firmware policy path plus shutdown LED policy, GPIO direction handling, topology-safe allocation, pinctrl, identity, default-state initialization, sleep-aware GPIO writes, and reference-compatible readback",'
        },
        [pscustomobject]@{
            Old = '        "physical_default_trigger_parity_required": generation >= 13,'
            New = '        "physical_default_trigger_parity_required": generation >= 13,' + "`n" + '        "physical_max_brightness_parity_required": generation >= 14,'
        }
    )

    foreach ($patch in $generation14Patches) {
        if (-not $controlledGenerator.Contains($patch.Old)) {
            throw "Could not apply bounded generation-14 synthesizer patch: $($patch.Old)"
        }
        $controlledGenerator = $controlledGenerator.Replace($patch.Old, $patch.New)
    }

    # Gen14 inherits the Gen13 default-trigger proof instead of dropping it at the generation boundary.
    $controlledTrial = $controlledTrial.Replace('if [[ "$GENERATION" == "13" ]]; then', 'if [[ "$GENERATION" -ge 13 ]]; then')

    $maxAnchor = '    [[ "$max" =~ ^[0-9]+$ && "$max" -ge 1 ]] || fail "candidate_led_invalid_max_brightness:$expected_name" 61'
    $maxInsertion = @'
    if [[ "$GENERATION" -ge 14 ]]; then
      echo "AURUM_PI4_LED_MAX_BRIGHTNESS_PARITY name=$expected_name expected=$expected_max actual=$max"
      [[ "$max" == "$expected_max" ]] || fail "candidate_max_brightness_differs_from_working_driver:$expected_name:$expected_max:$max" 68
    fi
'@
    $maxInsertion = $maxInsertion.Replace("`r`n", "`n").Replace("`r", "`n")
    if (-not $controlledTrial.Contains($maxAnchor)) {
        throw 'Could not locate the proven Pi4 max-brightness observation anchor for generation 14.'
    }
    $controlledTrial = $controlledTrial.Replace($maxAnchor, $maxAnchor + "`n" + $maxInsertion)

    $countAnchor = '  [[ "$tested" -eq "$expected_count" ]] || fail "candidate_led_count_mismatch:$tested:$expected_count" 63'
    $countInsertion = @'
  if [[ "$GENERATION" -ge 14 ]]; then
    echo "AURUM_PI4_DRIVER_CLASS_PARITY status=passed led_count=$tested max_brightness=true default_trigger=true"
  fi
'@
    $countInsertion = $countInsertion.Replace("`r`n", "`n").Replace("`r", "`n")
    if (-not $controlledTrial.Contains($countAnchor)) {
        throw 'Could not locate the Pi4 LED-count parity anchor for generation 14.'
    }
    $controlledTrial = $controlledTrial.Replace($countAnchor, $countAnchor + "`n" + $countInsertion)

    Write-Host "AURUM_PI4_DRIVER_GEN14 reference=led-class-observable-parity source=raspberrypi-linux-rpi-6.12.y bounded=true physical_max_brightness_parity=true inherited_default_trigger_parity=true"
}
