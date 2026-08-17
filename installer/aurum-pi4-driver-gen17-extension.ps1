#Requires -Version 5.1
Set-StrictMode -Version Latest

$gen16Extension = Join-Path $PSScriptRoot 'aurum-pi4-driver-gen16-extension.ps1'
if (-not (Test-Path -LiteralPath $gen16Extension -PathType Leaf)) {
    throw "Missing Aurum Pi4 generation-16 extension: $gen16Extension"
}
. $gen16Extension

if ($trialGeneration -ge 17) {
    $generation17Patches = @(
        [pscustomobject]@{
            Old = 'elif generation in {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16}:'
            New = 'elif generation in {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17}:'
        },
        [pscustomobject]@{
            Old = '            16: "fault-free physical driver lifecycle proof, requiring no new kernel BUG/WARNING/Oops/panic or sanitizer signatures across candidate load, bind, behavior exercise, unload, rollback, and working-driver restoration",'
            New = '            16: "fault-free physical driver lifecycle proof, requiring no new kernel BUG/WARNING/Oops/panic or sanitizer signatures across candidate load, bind, behavior exercise, unload, rollback, and working-driver restoration",' + "`n" + '            17: "repeatable two-cycle physical driver lifecycle proof, requiring a second candidate reload, bind, LED-class policy parity check, unload, rollback, and fault-free restored state without reboot",'
        },
        [pscustomobject]@{
            Old = 'if generation not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16}:'
            New = 'if generation not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17}:'
        },
        [pscustomobject]@{
            Old = '        16: "fault-free physical driver lifecycle proof across candidate load, bind, bounded LED exercise, unload, rollback, and restored working-driver state",'
            New = '        16: "fault-free physical driver lifecycle proof across candidate load, bind, bounded LED exercise, unload, rollback, and restored working-driver state",' + "`n" + '        17: "repeatable two-cycle physical driver lifecycle proof with second-cycle LED-class policy parity, unload, rollback, and kernel-health closure",'
        },
        [pscustomobject]@{
            Old = '        "kernel_fault_free_lifecycle_required": generation >= 16,'
            New = '        "kernel_fault_free_lifecycle_required": generation >= 16,' + "`n" + '        "repeatable_two_cycle_lifecycle_required": generation >= 17,'
        }
    )

    foreach ($patch in $generation17Patches) {
        if (-not $controlledGenerator.Contains($patch.Old)) {
            throw "Could not apply bounded generation-17 synthesizer patch: $($patch.Old)"
        }
        $controlledGenerator = $controlledGenerator.Replace($patch.Old, $patch.New)
    }

    $repeatAnchor = '    echo "AURUM_PI4_DRIVER_KERNEL_HEALTH status=passed new_fault_signatures=0 dmesg_delta_lines=$delta_lines ring_buffer_overlap=verified"'
    $repeatInsertion = @'
    if [[ "$GENERATION" -ge 17 ]]; then
      sudo dmesg >"$BACKUP_DIR/dmesg-before-cycle2.txt" 2>/dev/null || fail "dmesg_cycle2_baseline_unavailable" 82
      sudo insmod "$KO" || fail "cycle2_candidate_insmod_failed" 83
      [[ -d /sys/bus/platform/drivers/aurum-gpio-leds ]] || fail "cycle2_candidate_driver_registration_missing" 84
      printf '%s' "$DEVICE" | sudo tee "$DRIVER_DIR/unbind" >/dev/null
      [[ ! -L "$DRIVER_DIR/$DEVICE" ]] || fail "cycle2_working_driver_unbind_failed" 85
      printf '%s' "$DEVICE" | sudo tee /sys/bus/platform/drivers/aurum-gpio-leds/bind >/dev/null
      cycle2_bound="$(basename "$(readlink -f "/sys/bus/platform/devices/$DEVICE/driver" 2>/dev/null || true)")"
      [[ "$cycle2_bound" == "aurum-gpio-leds" ]] || fail "cycle2_candidate_bind_failed:$cycle2_bound" 86

      cycle2_checked=0
      while IFS=$'\t' read -r expected_name expected_brightness expected_trigger expected_device; do
        [[ -n "$expected_name" ]] || continue
        [[ "$expected_device" == "$TARGET_DEVICE_PATH" ]] || continue
        led="/sys/class/leds/$expected_name"
        [[ -e "$led" ]] || fail "cycle2_candidate_missing_led:$expected_name" 87
        actual_device="$(readlink -f "$led/device" 2>/dev/null || true)"
        [[ "$actual_device" == "$expected_device" ]] || fail "cycle2_candidate_led_wrong_device:$expected_name:$expected_device:$actual_device" 88
        expected_max="$(awk -F '\t' -v n="$expected_name" '$1 == n { print $2; exit }' "$BACKUP_DIR/original-behavior.tsv")"
        actual_max="$(cat "$led/max_brightness" 2>/dev/null || echo 0)"
        [[ -n "$expected_max" && "$actual_max" == "$expected_max" ]] || fail "cycle2_max_brightness_differs:$expected_name:$expected_max:$actual_max" 89
        trigger_line="$(cat "$led/trigger" 2>/dev/null || true)"
        actual_trigger="$(printf '%s' "$trigger_line" | sed -n 's/.*\[\([^]]*\)\].*/\1/p')"
        [[ "${actual_trigger:-none}" == "${expected_trigger:-none}" ]] || fail "cycle2_trigger_differs:$expected_name:${expected_trigger:-none}:${actual_trigger:-none}" 90
        cycle2_checked=$((cycle2_checked + 1))
      done <"$BACKUP_DIR/led-state.tsv"
      expected_count="$(cat "$BACKUP_DIR/original-behavior-led-count.txt")"
      [[ "$cycle2_checked" -eq "$expected_count" ]] || fail "cycle2_candidate_led_count_mismatch:$cycle2_checked:$expected_count" 91

      printf '%s' "$DEVICE" | sudo tee /sys/bus/platform/drivers/aurum-gpio-leds/unbind >/dev/null
      sudo rmmod aurum_gpio_leds || fail "cycle2_candidate_module_unload_failed" 92
      printf '%s' "$DEVICE" | sudo tee "$DRIVER_DIR/bind" >/dev/null
      restore_led_state
      cycle2_restored="$(basename "$(readlink -f "/sys/bus/platform/devices/$DEVICE/driver" 2>/dev/null || true)")"
      [[ "$cycle2_restored" == "$WORKING_DRIVER" ]] || fail "cycle2_rollback_rebind_failed:$cycle2_restored" 93
      [[ ! -d /sys/module/aurum_gpio_leds ]] || fail "cycle2_candidate_module_still_loaded" 94

      cycle2_rollback_checked=0
      while IFS=$'\t' read -r expected_name expected_brightness expected_trigger expected_device; do
        [[ -n "$expected_name" ]] || continue
        [[ "$expected_device" == "$TARGET_DEVICE_PATH" ]] || continue
        led="/sys/class/leds/$expected_name"
        [[ -e "$led" ]] || fail "cycle2_rollback_missing_led:$expected_name" 95
        actual_device="$(readlink -f "$led/device" 2>/dev/null || true)"
        [[ "$actual_device" == "$expected_device" ]] || fail "cycle2_rollback_led_wrong_device:$expected_name:$expected_device:$actual_device" 96
        expected_max="$(awk -F '\t' -v n="$expected_name" '$1 == n { print $2; exit }' "$BACKUP_DIR/original-behavior.tsv")"
        actual_max="$(cat "$led/max_brightness" 2>/dev/null || echo 0)"
        [[ -n "$expected_max" && "$actual_max" == "$expected_max" ]] || fail "cycle2_rollback_max_differs:$expected_name:$expected_max:$actual_max" 97
        trigger_line="$(cat "$led/trigger" 2>/dev/null || true)"
        actual_trigger="$(printf '%s' "$trigger_line" | sed -n 's/.*\[\([^]]*\)\].*/\1/p')"
        [[ "${actual_trigger:-none}" == "${expected_trigger:-none}" ]] || fail "cycle2_rollback_trigger_differs:$expected_name:${expected_trigger:-none}:${actual_trigger:-none}" 98
        cycle2_rollback_checked=$((cycle2_rollback_checked + 1))
      done <"$BACKUP_DIR/led-state.tsv"
      [[ "$cycle2_rollback_checked" -eq "$expected_count" ]] || fail "cycle2_rollback_led_count_mismatch:$cycle2_rollback_checked:$expected_count" 99

      sudo dmesg >"$BACKUP_DIR/dmesg-after-cycle2.txt" 2>/dev/null || fail "dmesg_cycle2_post_unavailable" 100
      if ! cycle2_delta_lines="$(python3 - "$BACKUP_DIR/dmesg-before-cycle2.txt" "$BACKUP_DIR/dmesg-after-cycle2.txt" "$BACKUP_DIR/dmesg-cycle2-delta.txt" <<'PY'
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
        raise SystemExit(101)

delta = after[overlap:]
delta_path.write_text("\n".join(delta) + ("\n" if delta else ""), encoding="utf-8")
print(len(delta))
PY
)"; then
        fail "dmesg_cycle2_window_unresolved" 101
      fi
      fault_pattern='BUG:|WARNING:|Oops:|kernel panic|Call Trace:|KASAN:|UBSAN:|general protection fault|use-after-free|refcount_t: underflow|scheduling while atomic|sleeping function called from invalid context'
      cycle2_fault_count="$(grep -Eic "$fault_pattern" "$BACKUP_DIR/dmesg-cycle2-delta.txt" || true)"
      [[ "$cycle2_fault_count" -eq 0 ]] || fail "kernel_fault_signature_after_cycle2:$cycle2_fault_count" 102
      echo "AURUM_PI4_DRIVER_REPEATABILITY status=passed cycles=2 second_cycle_led_class_parity=true second_cycle_rollback=true second_cycle_module_unloaded=true second_cycle_fault_signatures=0 second_cycle_dmesg_delta_lines=$cycle2_delta_lines"
    fi
'@
    $repeatInsertion = $repeatInsertion.Replace("`r`n", "`n").Replace("`r", "`n")
    if (-not $controlledTrial.Contains($repeatAnchor)) {
        throw 'Could not locate the generation-16 kernel-health anchor for generation 17.'
    }
    $controlledTrial = $controlledTrial.Replace($repeatAnchor, $repeatAnchor + "`n" + $repeatInsertion)

    Write-Host "AURUM_PI4_DRIVER_GEN17 reference=two-cycle-lifecycle-repeatability source=verified-gen16-rollback-path bounded=true cycles=2 no_reboot=true second_cycle_led_policy_parity=true"
}
