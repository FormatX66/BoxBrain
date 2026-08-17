#Requires -Version 5.1
Set-StrictMode -Version Latest

$gen12Extension = Join-Path $PSScriptRoot 'aurum-pi4-driver-gen12-extension.ps1'
if (-not (Test-Path -LiteralPath $gen12Extension -PathType Leaf)) {
    throw "Missing Aurum Pi4 generation-12 extension: $gen12Extension"
}
. $gen12Extension

if ($trialGeneration -ge 13) {
    $generation13Patches = @(
        [pscustomobject]@{
            Old = 'elif generation in {3, 4, 5, 6, 7, 8, 9, 10, 11, 12}:'
            New = 'elif generation in {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13}:'
        },
        [pscustomobject]@{
            Old = '            12: "reference-aligned shutdown LED policy, GPIO direction-flag handling, unified LED setter dispatch, counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, firmware LED policy flags, default-state initialization, sleep-aware GPIO LED writes, and learned Pi readback semantics",'
            New = '            12: "reference-aligned shutdown LED policy, GPIO direction-flag handling, unified LED setter dispatch, counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, firmware LED policy flags, default-state initialization, sleep-aware GPIO LED writes, and learned Pi readback semantics",' + "`n" + '            13: "reference-aligned LED-core firmware policy delegation with physical default-trigger parity, shutdown LED policy, GPIO direction-flag handling, unified LED setter dispatch, counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, default-state initialization, sleep-aware GPIO LED writes, and learned Pi readback semantics",'
        },
        [pscustomobject]@{
            Old = 'if generation not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12}:'
            New = 'if generation not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13}:'
        },
        [pscustomobject]@{
            Old = '        12: "reference-aligned shutdown LED policy plus GPIO direction-flag handling, unified LED setter dispatch, counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, firmware LED policy flags, default-state initialization, sleep-aware GPIO LED writes, and reference-compatible readback",'
            New = '        12: "reference-aligned shutdown LED policy plus GPIO direction-flag handling, unified LED setter dispatch, counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, firmware LED policy flags, default-state initialization, sleep-aware GPIO LED writes, and reference-compatible readback",' + "`n" + '        13: "reference-aligned LED-core firmware policy delegation with physical default-trigger parity plus shutdown LED policy, GPIO direction-flag handling, unified LED setter dispatch, counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, default-state initialization, sleep-aware GPIO LED writes, and reference-compatible readback",'
        },
        [pscustomobject]@{
            Old = '    if generation >= 5:'
            New = @'
    if generation >= 13:
        policy_setup = '''        if (!fwnode_property_present(child, "retain-state-suspended"))
            led->cdev.flags |= LED_CORE_SUSPENDRESUME;
        if (fwnode_property_present(child, "panic-indicator"))
            led->cdev.flags |= LED_PANIC_INDICATOR;
'''
    elif generation >= 5:
'@
        },
        [pscustomobject]@{
            Old = '    if generation >= 6:'
            New = @'
    if generation >= 13:
        post_register_policy_setup = '''        dev_info(dev,
                 "AURUM_GEN13_CORE_POLICY default_trigger=%s retain_shutdown=%d suspend_resume=%d panic=%d\n",
                 led->cdev.default_trigger ? led->cdev.default_trigger : "none",
                 !!(led->cdev.flags & LED_RETAIN_AT_SHUTDOWN),
                 !!(led->cdev.flags & LED_CORE_SUSPENDRESUME),
                 !!(led->cdev.flags & LED_PANIC_INDICATOR));
'''
    else:
        post_register_policy_setup = ""

    if generation >= 6:
'@
        },
        [pscustomobject]@{
            Old = '        }}\n{pinctrl_setup}{identity_setup}        used++;'
            New = '        }}\n{post_register_policy_setup}{pinctrl_setup}{identity_setup}        used++;'
        },
        [pscustomobject]@{
            Old = '        "shutdown_led_policy_aware": generation >= 12,'
            New = '        "shutdown_led_policy_aware": generation >= 12,' + "`n" + '        "led_core_fwnode_policy_delegated": generation >= 13,' + "`n" + '        "physical_default_trigger_parity_required": generation >= 13,'
        }
    )

    foreach ($patch in $generation13Patches) {
        if (-not $controlledGenerator.Contains($patch.Old)) {
            throw "Could not apply bounded generation-13 synthesizer patch: $($patch.Old)"
        }
        $controlledGenerator = $controlledGenerator.Replace($patch.Old, $patch.New)
    }

    $trialMarker = 'dmesg | tail -n 100 >"$BACKUP_DIR/dmesg-after-candidate-bind.txt" 2>/dev/null || true'
    $triggerParityBlock = @'

if [[ "$GENERATION" == "13" ]]; then
  : >"$BACKUP_DIR/candidate-trigger-parity.tsv"
  trigger_checked=0
  while IFS=$'\t' read -r expected_name original_brightness expected_trigger original_device; do
    [[ -n "$expected_name" ]] || continue
    [[ "$original_device" == "$TARGET_DEVICE_PATH" ]] || continue
    led="/sys/class/leds/$expected_name"
    [[ -e "$led" ]] || fail "candidate_trigger_led_missing:$expected_name" 65
    trigger_line="$(cat "$led/trigger" 2>/dev/null || true)"
    actual_trigger="$(printf '%s' "$trigger_line" | sed -n 's/.*\[\([^]]*\)\].*/\1/p')"
    echo "AURUM_PI4_LED_TRIGGER_PARITY name=$expected_name expected=${expected_trigger:-none} actual=${actual_trigger:-none}"
    printf '%s\t%s\t%s\n' "$expected_name" "$expected_trigger" "$actual_trigger" >>"$BACKUP_DIR/candidate-trigger-parity.tsv"
    [[ "$actual_trigger" == "$expected_trigger" ]] || fail "candidate_default_trigger_differs_from_working_driver:$expected_name:$expected_trigger:$actual_trigger" 66
    trigger_checked=$((trigger_checked + 1))
  done <"$BACKUP_DIR/led-state.tsv"
  expected_trigger_count="$(cat "$BACKUP_DIR/original-behavior-led-count.txt")"
  [[ "$trigger_checked" -eq "$expected_trigger_count" ]] || fail "candidate_trigger_count_mismatch:$trigger_checked:$expected_trigger_count" 67
  core_policy_lines="$(grep -c 'AURUM_GEN13_CORE_POLICY' "$BACKUP_DIR/dmesg-after-candidate-bind.txt" || true)"
  [[ "$core_policy_lines" -ge "$expected_trigger_count" ]] || fail "candidate_led_core_policy_log_count_mismatch:$core_policy_lines:$expected_trigger_count" 68
  echo "AURUM_PI4_DRIVER_TRIGGER_PARITY status=passed led_count=$trigger_checked led_core_policy_paths=$core_policy_lines"
fi
'@
    if (-not $controlledTrial.Contains($trialMarker)) {
        throw 'Could not locate generation-13 physical trigger-parity insertion point.'
    }
    $controlledTrial = $controlledTrial.Replace($trialMarker, $trialMarker + $triggerParityBlock)

    Write-Host "AURUM_PI4_DRIVER_GEN13 reference=led-core-fwnode-policy-delegation source=raspberrypi-linux-rpi-6.12.y bounded=true physical_default_trigger_parity=true"
}
