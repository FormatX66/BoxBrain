#Requires -Version 5.1
Set-StrictMode -Version Latest

$gen18Extension = Join-Path $PSScriptRoot 'aurum-pi4-driver-gen18-extension.ps1'
if (-not (Test-Path -LiteralPath $gen18Extension -PathType Leaf)) {
    throw "Missing Aurum Pi4 generation-18 extension: $gen18Extension"
}
. $gen18Extension

if ($trialGeneration -ge 19) {
    $generation19Patches = @(
        [pscustomobject]@{
            Old = 'elif generation in {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18}:'
            New = 'elif generation in {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19}:'
        },
        [pscustomobject]@{
            Old = '            18: "four-cycle physical driver lifecycle stress proof, requiring two additional candidate reload/bind/unload/rollback cycles with LED-class policy parity and zero new kernel fault signatures without reboot",'
            New = '            18: "four-cycle physical driver lifecycle stress proof, requiring two additional candidate reload/bind/unload/rollback cycles with LED-class policy parity and zero new kernel fault signatures without reboot",' + "`n" + '            19: "eight-cycle physical driver lifecycle and write/readback stress proof, requiring four more candidate reload/bind cycles with exact working-driver LED behavior parity, unload, rollback, and zero new kernel fault signatures without reboot",'
        },
        [pscustomobject]@{
            Old = 'if generation not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18}:'
            New = 'if generation not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19}:'
        },
        [pscustomobject]@{
            Old = '        18: "four-cycle physical driver lifecycle stress proof with repeated LED-class policy parity, module unload, rollback, and kernel-health closure",'
            New = '        18: "four-cycle physical driver lifecycle stress proof with repeated LED-class policy parity, module unload, rollback, and kernel-health closure",' + "`n" + '        19: "eight-cycle physical driver lifecycle and LED write/readback stress proof with repeated behavior parity, module unload, rollback, and kernel-health closure",'
        },
        [pscustomobject]@{
            Old = '        "four_cycle_lifecycle_stress_required": generation >= 18,'
            New = '        "four_cycle_lifecycle_stress_required": generation >= 18,' + "`n" + '        "eight_cycle_write_readback_stress_required": generation >= 19,'
        }
    )

    foreach ($patch in $generation19Patches) {
        if (-not $controlledGenerator.Contains($patch.Old)) {
            throw "Could not apply bounded generation-19 synthesizer patch: $($patch.Old)"
        }
        $controlledGenerator = $controlledGenerator.Replace($patch.Old, $patch.New)
    }

    $stressAnchor = '        echo "AURUM_PI4_DRIVER_STRESS status=passed cycles_total=4 added_cycles=2 led_class_parity=true rollback=true candidate_module_unloaded=true new_fault_signatures=0 dmesg_delta_lines=$stress_delta_lines no_reboot=true"'
    $stressInsertion = @'
      if [[ "$GENERATION" -ge 19 ]]; then
        sudo dmesg >"$BACKUP_DIR/dmesg-before-gen19-stress.txt" 2>/dev/null || fail "dmesg_gen19_baseline_unavailable" 125
        gen19_cycles=0
        for gen19_cycle in 5 6 7 8; do
          sudo insmod "$KO" || fail "gen19_candidate_insmod_failed:$gen19_cycle" 126
          [[ -d /sys/bus/platform/drivers/aurum-gpio-leds ]] || fail "gen19_candidate_driver_registration_missing:$gen19_cycle" 127
          printf '%s' "$DEVICE" | sudo tee "$DRIVER_DIR/unbind" >/dev/null
          [[ ! -L "$DRIVER_DIR/$DEVICE" ]] || fail "gen19_working_driver_unbind_failed:$gen19_cycle" 128
          printf '%s' "$DEVICE" | sudo tee /sys/bus/platform/drivers/aurum-gpio-leds/bind >/dev/null
          gen19_bound="$(basename "$(readlink -f "/sys/bus/platform/devices/$DEVICE/driver" 2>/dev/null || true)")"
          [[ "$gen19_bound" == "aurum-gpio-leds" ]] || fail "gen19_candidate_bind_failed:$gen19_cycle:$gen19_bound" 129

          gen19_tested=0
          while IFS=$'\t' read -r expected_name expected_max expected_zero expected_one expected_zero2; do
            [[ -n "$expected_name" ]] || continue
            led="/sys/class/leds/$expected_name"
            [[ -e "$led" ]] || fail "gen19_candidate_missing_led:$gen19_cycle:$expected_name" 130
            actual_device="$(readlink -f "$led/device" 2>/dev/null || true)"
            [[ "$actual_device" == "$TARGET_DEVICE_PATH" ]] || fail "gen19_candidate_led_wrong_device:$gen19_cycle:$expected_name:$actual_device" 131
            actual_max="$(cat "$led/max_brightness" 2>/dev/null || echo 0)"
            [[ "$actual_max" == "$expected_max" ]] || fail "gen19_max_brightness_differs:$gen19_cycle:$expected_name:$expected_max:$actual_max" 132
            if [[ -w "$led/trigger" ]]; then
              printf '%s' none | sudo tee "$led/trigger" >/dev/null
            fi
            printf '%s' 0 | sudo tee "$led/brightness" >/dev/null
            gen19_zero="$(cat "$led/brightness")"
            printf '%s' 1 | sudo tee "$led/brightness" >/dev/null
            gen19_one="$(cat "$led/brightness")"
            printf '%s' 0 | sudo tee "$led/brightness" >/dev/null
            gen19_zero2="$(cat "$led/brightness")"
            [[ "$gen19_zero" == "$expected_zero" && "$gen19_one" == "$expected_one" && "$gen19_zero2" == "$expected_zero2" ]] || fail "gen19_behavior_differs:$gen19_cycle:$expected_name:$expected_zero,$expected_one,$expected_zero2:$gen19_zero,$gen19_one,$gen19_zero2" 133
            gen19_tested=$((gen19_tested + 1))
          done <"$BACKUP_DIR/original-behavior.tsv"
          expected_count="$(cat "$BACKUP_DIR/original-behavior-led-count.txt")"
          [[ "$gen19_tested" -eq "$expected_count" ]] || fail "gen19_candidate_led_count_mismatch:$gen19_cycle:$gen19_tested:$expected_count" 134
          restore_led_state

          printf '%s' "$DEVICE" | sudo tee /sys/bus/platform/drivers/aurum-gpio-leds/unbind >/dev/null
          sudo rmmod aurum_gpio_leds || fail "gen19_candidate_module_unload_failed:$gen19_cycle" 135
          printf '%s' "$DEVICE" | sudo tee "$DRIVER_DIR/bind" >/dev/null
          restore_led_state
          gen19_restored="$(basename "$(readlink -f "/sys/bus/platform/devices/$DEVICE/driver" 2>/dev/null || true)")"
          [[ "$gen19_restored" == "$WORKING_DRIVER" ]] || fail "gen19_rollback_rebind_failed:$gen19_cycle:$gen19_restored" 136
          [[ ! -d /sys/module/aurum_gpio_leds ]] || fail "gen19_candidate_module_still_loaded:$gen19_cycle" 137

          gen19_rollback_checked=0
          while IFS=$'\t' read -r expected_name expected_brightness expected_trigger expected_device; do
            [[ -n "$expected_name" ]] || continue
            [[ "$expected_device" == "$TARGET_DEVICE_PATH" ]] || continue
            led="/sys/class/leds/$expected_name"
            [[ -e "$led" ]] || fail "gen19_rollback_missing_led:$gen19_cycle:$expected_name" 138
            actual_device="$(readlink -f "$led/device" 2>/dev/null || true)"
            [[ "$actual_device" == "$expected_device" ]] || fail "gen19_rollback_led_wrong_device:$gen19_cycle:$expected_name:$expected_device:$actual_device" 139
            expected_max="$(awk -F '\t' -v n="$expected_name" '$1 == n { print $2; exit }' "$BACKUP_DIR/original-behavior.tsv")"
            actual_max="$(cat "$led/max_brightness" 2>/dev/null || echo 0)"
            [[ -n "$expected_max" && "$actual_max" == "$expected_max" ]] || fail "gen19_rollback_max_differs:$gen19_cycle:$expected_name:$expected_max:$actual_max" 140
            trigger_line="$(cat "$led/trigger" 2>/dev/null || true)"
            actual_trigger="$(printf '%s' "$trigger_line" | sed -n 's/.*\[\([^]]*\)\].*/\1/p')"
            [[ "${actual_trigger:-none}" == "${expected_trigger:-none}" ]] || fail "gen19_rollback_trigger_differs:$gen19_cycle:$expected_name:${expected_trigger:-none}:${actual_trigger:-none}" 141
            gen19_rollback_checked=$((gen19_rollback_checked + 1))
          done <"$BACKUP_DIR/led-state.tsv"
          [[ "$gen19_rollback_checked" -eq "$expected_count" ]] || fail "gen19_rollback_led_count_mismatch:$gen19_cycle:$gen19_rollback_checked:$expected_count" 142
          gen19_cycles=$((gen19_cycles + 1))
          echo "AURUM_PI4_DRIVER_GEN19_CYCLE status=passed cycle=$gen19_cycle behavior_parity=true rollback=true module_unloaded=true"
        done
        [[ "$gen19_cycles" -eq 4 ]] || fail "gen19_cycle_count_mismatch:$gen19_cycles" 143

        sudo dmesg >"$BACKUP_DIR/dmesg-after-gen19-stress.txt" 2>/dev/null || fail "dmesg_gen19_post_unavailable" 144
        if ! gen19_delta_lines="$(python3 - "$BACKUP_DIR/dmesg-before-gen19-stress.txt" "$BACKUP_DIR/dmesg-after-gen19-stress.txt" "$BACKUP_DIR/dmesg-gen19-delta.txt" <<'PY'
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
        raise SystemExit(145)
delta = after[overlap:]
delta_path.write_text("\n".join(delta) + ("\n" if delta else ""), encoding="utf-8")
print(len(delta))
PY
)"; then
          fail "dmesg_gen19_window_unresolved" 145
        fi
        fault_pattern='BUG:|WARNING:|Oops:|kernel panic|Call Trace:|KASAN:|UBSAN:|general protection fault|use-after-free|refcount_t: underflow|scheduling while atomic|sleeping function called from invalid context'
        gen19_fault_count="$(grep -Eic "$fault_pattern" "$BACKUP_DIR/dmesg-gen19-delta.txt" || true)"
        [[ "$gen19_fault_count" -eq 0 ]] || fail "kernel_fault_signature_after_gen19_stress:$gen19_fault_count" 146
        echo "AURUM_PI4_DRIVER_GEN19_STRESS status=passed cycles_total=8 added_cycles=4 behavior_parity=true rollback=true candidate_module_unloaded=true new_fault_signatures=0 dmesg_delta_lines=$gen19_delta_lines no_reboot=true"
      fi
'@
    $stressInsertion = $stressInsertion.Replace("`r`n", "`n").Replace("`r", "`n")
    if (-not $controlledTrial.Contains($stressAnchor)) {
        throw 'Could not locate the generation-18 stress anchor for generation 19.'
    }
    $controlledTrial = $controlledTrial.Replace($stressAnchor, $stressAnchor + "`n" + $stressInsertion)

    Write-Host "AURUM_PI4_DRIVER_GEN19 reference=eight-cycle-write-readback-stress source=verified-gen18-stress bounded=true cycles_total=8 no_reboot=true behavior_parity=true"
}
