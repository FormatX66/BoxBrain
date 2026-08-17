#Requires -Version 5.1
Set-StrictMode -Version Latest

$gen17Extension = Join-Path $PSScriptRoot 'aurum-pi4-driver-gen17-extension.ps1'
if (-not (Test-Path -LiteralPath $gen17Extension -PathType Leaf)) {
    throw "Missing Aurum Pi4 generation-17 extension: $gen17Extension"
}
. $gen17Extension

if ($trialGeneration -ge 18) {
    $generation18Patches = @(
        [pscustomobject]@{
            Old = 'elif generation in {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17}:'
            New = 'elif generation in {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18}:'
        },
        [pscustomobject]@{
            Old = '            17: "repeatable two-cycle physical driver lifecycle proof, requiring a second candidate reload, bind, LED-class policy parity check, unload, rollback, and fault-free restored state without reboot",'
            New = '            17: "repeatable two-cycle physical driver lifecycle proof, requiring a second candidate reload, bind, LED-class policy parity check, unload, rollback, and fault-free restored state without reboot",' + "`n" + '            18: "four-cycle physical driver lifecycle stress proof, requiring two additional candidate reload/bind/unload/rollback cycles with LED-class policy parity and zero new kernel fault signatures without reboot",'
        },
        [pscustomobject]@{
            Old = 'if generation not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17}:'
            New = 'if generation not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18}:'
        },
        [pscustomobject]@{
            Old = '        17: "repeatable two-cycle physical driver lifecycle proof with second-cycle LED-class policy parity, unload, rollback, and kernel-health closure",'
            New = '        17: "repeatable two-cycle physical driver lifecycle proof with second-cycle LED-class policy parity, unload, rollback, and kernel-health closure",' + "`n" + '        18: "four-cycle physical driver lifecycle stress proof with repeated LED-class policy parity, module unload, rollback, and kernel-health closure",'
        },
        [pscustomobject]@{
            Old = '        "repeatable_two_cycle_lifecycle_required": generation >= 17,'
            New = '        "repeatable_two_cycle_lifecycle_required": generation >= 17,' + "`n" + '        "four_cycle_lifecycle_stress_required": generation >= 18,'
        }
    )

    foreach ($patch in $generation18Patches) {
        if (-not $controlledGenerator.Contains($patch.Old)) {
            throw "Could not apply bounded generation-18 synthesizer patch: $($patch.Old)"
        }
        $controlledGenerator = $controlledGenerator.Replace($patch.Old, $patch.New)
    }

    $stressAnchor = '      echo "AURUM_PI4_DRIVER_REPEATABILITY status=passed cycles=2 second_cycle_led_class_parity=true second_cycle_rollback=true second_cycle_module_unloaded=true second_cycle_fault_signatures=0 second_cycle_dmesg_delta_lines=$cycle2_delta_lines"'
    $stressInsertion = @'
      if [[ "$GENERATION" -ge 18 ]]; then
        sudo dmesg >"$BACKUP_DIR/dmesg-before-stress.txt" 2>/dev/null || fail "dmesg_stress_baseline_unavailable" 103
        stress_cycles=0
        for stress_cycle in 3 4; do
          sudo insmod "$KO" || fail "stress_candidate_insmod_failed:$stress_cycle" 104
          [[ -d /sys/bus/platform/drivers/aurum-gpio-leds ]] || fail "stress_candidate_driver_registration_missing:$stress_cycle" 105
          printf '%s' "$DEVICE" | sudo tee "$DRIVER_DIR/unbind" >/dev/null
          [[ ! -L "$DRIVER_DIR/$DEVICE" ]] || fail "stress_working_driver_unbind_failed:$stress_cycle" 106
          printf '%s' "$DEVICE" | sudo tee /sys/bus/platform/drivers/aurum-gpio-leds/bind >/dev/null
          stress_bound="$(basename "$(readlink -f "/sys/bus/platform/devices/$DEVICE/driver" 2>/dev/null || true)")"
          [[ "$stress_bound" == "aurum-gpio-leds" ]] || fail "stress_candidate_bind_failed:$stress_cycle:$stress_bound" 107

          stress_checked=0
          while IFS=$'\t' read -r expected_name expected_brightness expected_trigger expected_device; do
            [[ -n "$expected_name" ]] || continue
            [[ "$expected_device" == "$TARGET_DEVICE_PATH" ]] || continue
            led="/sys/class/leds/$expected_name"
            [[ -e "$led" ]] || fail "stress_candidate_missing_led:$stress_cycle:$expected_name" 108
            actual_device="$(readlink -f "$led/device" 2>/dev/null || true)"
            [[ "$actual_device" == "$expected_device" ]] || fail "stress_candidate_led_wrong_device:$stress_cycle:$expected_name:$expected_device:$actual_device" 109
            expected_max="$(awk -F '\t' -v n="$expected_name" '$1 == n { print $2; exit }' "$BACKUP_DIR/original-behavior.tsv")"
            actual_max="$(cat "$led/max_brightness" 2>/dev/null || echo 0)"
            [[ -n "$expected_max" && "$actual_max" == "$expected_max" ]] || fail "stress_max_brightness_differs:$stress_cycle:$expected_name:$expected_max:$actual_max" 110
            trigger_line="$(cat "$led/trigger" 2>/dev/null || true)"
            actual_trigger="$(printf '%s' "$trigger_line" | sed -n 's/.*\[\([^]]*\)\].*/\1/p')"
            [[ "${actual_trigger:-none}" == "${expected_trigger:-none}" ]] || fail "stress_trigger_differs:$stress_cycle:$expected_name:${expected_trigger:-none}:${actual_trigger:-none}" 111
            stress_checked=$((stress_checked + 1))
          done <"$BACKUP_DIR/led-state.tsv"
          expected_count="$(cat "$BACKUP_DIR/original-behavior-led-count.txt")"
          [[ "$stress_checked" -eq "$expected_count" ]] || fail "stress_candidate_led_count_mismatch:$stress_cycle:$stress_checked:$expected_count" 112

          printf '%s' "$DEVICE" | sudo tee /sys/bus/platform/drivers/aurum-gpio-leds/unbind >/dev/null
          sudo rmmod aurum_gpio_leds || fail "stress_candidate_module_unload_failed:$stress_cycle" 113
          printf '%s' "$DEVICE" | sudo tee "$DRIVER_DIR/bind" >/dev/null
          restore_led_state
          stress_restored="$(basename "$(readlink -f "/sys/bus/platform/devices/$DEVICE/driver" 2>/dev/null || true)")"
          [[ "$stress_restored" == "$WORKING_DRIVER" ]] || fail "stress_rollback_rebind_failed:$stress_cycle:$stress_restored" 114
          [[ ! -d /sys/module/aurum_gpio_leds ]] || fail "stress_candidate_module_still_loaded:$stress_cycle" 115

          rollback_checked_stress=0
          while IFS=$'\t' read -r expected_name expected_brightness expected_trigger expected_device; do
            [[ -n "$expected_name" ]] || continue
            [[ "$expected_device" == "$TARGET_DEVICE_PATH" ]] || continue
            led="/sys/class/leds/$expected_name"
            [[ -e "$led" ]] || fail "stress_rollback_missing_led:$stress_cycle:$expected_name" 116
            actual_device="$(readlink -f "$led/device" 2>/dev/null || true)"
            [[ "$actual_device" == "$expected_device" ]] || fail "stress_rollback_led_wrong_device:$stress_cycle:$expected_name:$expected_device:$actual_device" 117
            expected_max="$(awk -F '\t' -v n="$expected_name" '$1 == n { print $2; exit }' "$BACKUP_DIR/original-behavior.tsv")"
            actual_max="$(cat "$led/max_brightness" 2>/dev/null || echo 0)"
            [[ -n "$expected_max" && "$actual_max" == "$expected_max" ]] || fail "stress_rollback_max_differs:$stress_cycle:$expected_name:$expected_max:$actual_max" 118
            trigger_line="$(cat "$led/trigger" 2>/dev/null || true)"
            actual_trigger="$(printf '%s' "$trigger_line" | sed -n 's/.*\[\([^]]*\)\].*/\1/p')"
            [[ "${actual_trigger:-none}" == "${expected_trigger:-none}" ]] || fail "stress_rollback_trigger_differs:$stress_cycle:$expected_name:${expected_trigger:-none}:${actual_trigger:-none}" 119
            rollback_checked_stress=$((rollback_checked_stress + 1))
          done <"$BACKUP_DIR/led-state.tsv"
          [[ "$rollback_checked_stress" -eq "$expected_count" ]] || fail "stress_rollback_led_count_mismatch:$stress_cycle:$rollback_checked_stress:$expected_count" 120
          stress_cycles=$((stress_cycles + 1))
          echo "AURUM_PI4_DRIVER_STRESS_CYCLE status=passed cycle=$stress_cycle led_class_parity=true rollback=true module_unloaded=true"
        done
        [[ "$stress_cycles" -eq 2 ]] || fail "stress_cycle_count_mismatch:$stress_cycles" 121

        sudo dmesg >"$BACKUP_DIR/dmesg-after-stress.txt" 2>/dev/null || fail "dmesg_stress_post_unavailable" 122
        if ! stress_delta_lines="$(python3 - "$BACKUP_DIR/dmesg-before-stress.txt" "$BACKUP_DIR/dmesg-after-stress.txt" "$BACKUP_DIR/dmesg-stress-delta.txt" <<'PY'
from pathlib import Path
import sys

before_path, after_path, delta_path = map(Path, sys.argv[1:4])
before = before_path.read_text(encoding="utf-8", errors="replace").splitlines()
after = after_path.read_text(encoding="utf-8", errors="replace").splitlines()

if not before:
    overlap = 0
else:
    overlap = None
    first = after[0] if after else None
    if first is not None:
        for index, line in enumerate(before):
            if line != first:
                continue
            candidate = before[index:]
            if len(candidate) <= len(after) and candidate == after[: len(candidate)]:
                overlap = len(candidate)
                break
    if overlap is None and after == before:
        overlap = len(before)
    if overlap is None:
        raise SystemExit(123)

delta = after[overlap:]
delta_path.write_text("\n".join(delta) + ("\n" if delta else ""), encoding="utf-8")
print(len(delta))
PY
)"; then
          fail "dmesg_stress_window_unresolved" 123
        fi
        fault_pattern='BUG:|WARNING:|Oops:|kernel panic|Call Trace:|KASAN:|UBSAN:|general protection fault|use-after-free|refcount_t: underflow|scheduling while atomic|sleeping function called from invalid context'
        stress_fault_count="$(grep -Eic "$fault_pattern" "$BACKUP_DIR/dmesg-stress-delta.txt" || true)"
        [[ "$stress_fault_count" -eq 0 ]] || fail "kernel_fault_signature_after_stress:$stress_fault_count" 124
        echo "AURUM_PI4_DRIVER_STRESS status=passed cycles_total=4 added_cycles=2 led_class_parity=true rollback=true candidate_module_unloaded=true new_fault_signatures=0 dmesg_delta_lines=$stress_delta_lines no_reboot=true"
      fi
'@
    $stressInsertion = $stressInsertion.Replace("`r`n", "`n").Replace("`r", "`n")
    if (-not $controlledTrial.Contains($stressAnchor)) {
        throw 'Could not locate the generation-17 repeatability anchor for generation 18.'
    }
    $controlledTrial = $controlledTrial.Replace($stressAnchor, $stressAnchor + "`n" + $stressInsertion)

    Write-Host "AURUM_PI4_DRIVER_GEN18 reference=four-cycle-lifecycle-stress source=verified-gen17-repeatability bounded=true cycles_total=4 no_reboot=true led_policy_parity=true"
}
