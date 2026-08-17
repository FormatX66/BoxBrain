#Requires -Version 5.1
Set-StrictMode -Version Latest

$gen14Extension = Join-Path $PSScriptRoot 'aurum-pi4-driver-gen14-extension.ps1'
if (-not (Test-Path -LiteralPath $gen14Extension -PathType Leaf)) {
    throw "Missing Aurum Pi4 generation-14 extension: $gen14Extension"
}
. $gen14Extension

if ($trialGeneration -ge 15) {
    $generation15Patches = @(
        [pscustomobject]@{
            Old = 'elif generation in {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14}:'
            New = 'elif generation in {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}:'
        },
        [pscustomobject]@{
            Old = '            14: "physical LED-class max-brightness and default-trigger parity closure over the reference-aligned LED-core firmware policy path, shutdown LED policy, GPIO direction handling, topology-safe allocation, pinctrl, identity, default-state initialization, sleep-aware GPIO writes, and readback semantics",'
            New = '            14: "physical LED-class max-brightness and default-trigger parity closure over the reference-aligned LED-core firmware policy path, shutdown LED policy, GPIO direction handling, topology-safe allocation, pinctrl, identity, default-state initialization, sleep-aware GPIO writes, and readback semantics",' + "`n" + '            15: "post-trial rollback state equivalence proof over the physically validated LED-class driver, including original driver rebound, candidate module unload, target sysfs topology, max-brightness, and trigger restoration",'
        },
        [pscustomobject]@{
            Old = 'if generation not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14}:'
            New = 'if generation not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}:'
        },
        [pscustomobject]@{
            Old = '        14: "physical LED-class max-brightness and default-trigger parity closure over the reference-aligned LED-core firmware policy path plus shutdown LED policy, GPIO direction handling, topology-safe allocation, pinctrl, identity, default-state initialization, sleep-aware GPIO writes, and reference-compatible readback",'
            New = '        14: "physical LED-class max-brightness and default-trigger parity closure over the reference-aligned LED-core firmware policy path plus shutdown LED policy, GPIO direction handling, topology-safe allocation, pinctrl, identity, default-state initialization, sleep-aware GPIO writes, and reference-compatible readback",' + "`n" + '        15: "post-trial rollback state equivalence proof over the physically validated LED-class driver, including original driver rebound, candidate module unload, target sysfs topology, max-brightness, and trigger restoration",'
        },
        [pscustomobject]@{
            Old = '        "physical_max_brightness_parity_required": generation >= 14,'
            New = '        "physical_max_brightness_parity_required": generation >= 14,' + "`n" + '        "post_rollback_sysfs_parity_required": generation >= 15,' + "`n" + '        "candidate_module_unload_required": generation >= 15,'
        }
    )

    foreach ($patch in $generation15Patches) {
        if (-not $controlledGenerator.Contains($patch.Old)) {
            throw "Could not apply bounded generation-15 synthesizer patch: $($patch.Old)"
        }
        $controlledGenerator = $controlledGenerator.Replace($patch.Old, $patch.New)
    }

    $rollbackAnchor = '[[ "$RESTORED_DRIVER" == "$WORKING_DRIVER" ]] || fail "rollback_rebind_failed:$RESTORED_DRIVER" 64'
    $rollbackInsertion = @'
if [[ "$GENERATION" -ge 15 ]]; then
  [[ ! -d /sys/module/aurum_gpio_leds ]] || fail "candidate_module_still_loaded_after_rollback" 69
  rollback_checked=0
  while IFS=$'\t' read -r expected_name expected_brightness expected_trigger expected_device; do
    [[ -n "$expected_name" ]] || continue
    [[ "$expected_device" == "$TARGET_DEVICE_PATH" ]] || continue
    led="/sys/class/leds/$expected_name"
    [[ -e "$led" ]] || fail "rollback_missing_led:$expected_name" 70
    actual_device="$(readlink -f "$led/device" 2>/dev/null || true)"
    [[ "$actual_device" == "$expected_device" ]] || fail "rollback_led_wrong_device:$expected_name:$expected_device:$actual_device" 71
    expected_max="$(awk -F '\t' -v n="$expected_name" '$1 == n { print $2; exit }' "$BACKUP_DIR/original-behavior.tsv")"
    actual_max="$(cat "$led/max_brightness" 2>/dev/null || echo 0)"
    [[ -n "$expected_max" && "$actual_max" == "$expected_max" ]] || fail "rollback_max_brightness_differs:$expected_name:$expected_max:$actual_max" 72
    trigger_line="$(cat "$led/trigger" 2>/dev/null || true)"
    actual_trigger="$(printf '%s' "$trigger_line" | sed -n 's/.*\[\([^]]*\)\].*/\1/p')"
    [[ "${actual_trigger:-none}" == "${expected_trigger:-none}" ]] || fail "rollback_trigger_differs:$expected_name:${expected_trigger:-none}:${actual_trigger:-none}" 73
    if [[ "${expected_trigger:-none}" == "none" ]]; then
      actual_brightness="$(cat "$led/brightness" 2>/dev/null || true)"
      [[ "$actual_brightness" == "$expected_brightness" ]] || fail "rollback_static_brightness_differs:$expected_name:$expected_brightness:$actual_brightness" 74
    fi
    echo "AURUM_PI4_LED_ROLLBACK_PARITY name=$expected_name device=$actual_device max=$actual_max trigger=${actual_trigger:-none} static_brightness_checked=$([[ "${expected_trigger:-none}" == "none" ]] && echo true || echo false)"
    rollback_checked=$((rollback_checked + 1))
  done <"$BACKUP_DIR/led-state.tsv"
  expected_count="$(cat "$BACKUP_DIR/original-behavior-led-count.txt")"
  [[ "$rollback_checked" -eq "$expected_count" ]] || fail "rollback_led_count_mismatch:$rollback_checked:$expected_count" 75
  echo "AURUM_PI4_DRIVER_ROLLBACK_PARITY status=passed led_count=$rollback_checked original_driver=$RESTORED_DRIVER candidate_module_unloaded=true sysfs_topology=true max_brightness=true default_trigger=true"
fi
'@
    $rollbackInsertion = $rollbackInsertion.Replace("`r`n", "`n").Replace("`r", "`n")
    if (-not $controlledTrial.Contains($rollbackAnchor)) {
        throw 'Could not locate the proven Pi4 rollback-rebind anchor for generation 15.'
    }
    $controlledTrial = $controlledTrial.Replace($rollbackAnchor, $rollbackAnchor + "`n" + $rollbackInsertion)

    Write-Host "AURUM_PI4_DRIVER_GEN15 reference=post-trial-rollback-state-equivalence source=verified-working-driver-observation bounded=true candidate_module_unload=true target_sysfs_parity=true"
}
