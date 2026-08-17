#Requires -Version 5.1
Set-StrictMode -Version Latest

$gen15Extension = Join-Path $PSScriptRoot 'aurum-pi4-driver-gen15-extension.ps1'
if (-not (Test-Path -LiteralPath $gen15Extension -PathType Leaf)) {
    throw "Missing Aurum Pi4 generation-15 extension: $gen15Extension"
}
. $gen15Extension

if ($trialGeneration -ge 16) {
    $generation16Patches = @(
        [pscustomobject]@{
            Old = 'elif generation in {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}:'
            New = 'elif generation in {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16}:'
        },
        [pscustomobject]@{
            Old = '            15: "post-trial rollback state equivalence proof over the physically validated LED-class driver, including original driver rebound, candidate module unload, target sysfs topology, max-brightness, and trigger restoration",'
            New = '            15: "post-trial rollback state equivalence proof over the physically validated LED-class driver, including original driver rebound, candidate module unload, target sysfs topology, max-brightness, and trigger restoration",' + "`n" + '            16: "fault-free physical driver lifecycle proof, requiring no new kernel BUG/WARNING/Oops/panic or sanitizer signatures across candidate load, bind, behavior exercise, unload, rollback, and working-driver restoration",'
        },
        [pscustomobject]@{
            Old = 'if generation not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}:'
            New = 'if generation not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16}:'
        },
        [pscustomobject]@{
            Old = '        15: "post-trial rollback state equivalence proof over the physically validated LED-class driver, including original driver rebound, candidate module unload, target sysfs topology, max-brightness, and trigger restoration",'
            New = '        15: "post-trial rollback state equivalence proof over the physically validated LED-class driver, including original driver rebound, candidate module unload, target sysfs topology, max-brightness, and trigger restoration",' + "`n" + '        16: "fault-free physical driver lifecycle proof across candidate load, bind, bounded LED exercise, unload, rollback, and restored working-driver state",'
        },
        [pscustomobject]@{
            Old = '        "candidate_module_unload_required": generation >= 15,'
            New = '        "candidate_module_unload_required": generation >= 15,' + "`n" + '        "kernel_fault_free_lifecycle_required": generation >= 16,'
        }
    )

    foreach ($patch in $generation16Patches) {
        if (-not $controlledGenerator.Contains($patch.Old)) {
            throw "Could not apply bounded generation-16 synthesizer patch: $($patch.Old)"
        }
        $controlledGenerator = $controlledGenerator.Replace($patch.Old, $patch.New)
    }

    $insmodAnchor = 'sudo insmod "$KO"'
    $baselineInsertion = @'
if [[ "$GENERATION" -ge 16 ]]; then
  sudo dmesg >"$BACKUP_DIR/dmesg-before-trial.txt" 2>/dev/null || fail "dmesg_baseline_unavailable" 76
fi
'@
    $baselineInsertion = $baselineInsertion.Replace("`r`n", "`n").Replace("`r", "`n")
    if (-not $controlledTrial.Contains($insmodAnchor)) {
        throw 'Could not locate the proven Pi4 candidate-insmod anchor for generation 16.'
    }
    $controlledTrial = $controlledTrial.Replace($insmodAnchor, $baselineInsertion + "`n" + $insmodAnchor)

    $rollbackHealthAnchor = '  echo "AURUM_PI4_DRIVER_ROLLBACK_PARITY status=passed led_count=$rollback_checked original_driver=$RESTORED_DRIVER candidate_module_unloaded=true sysfs_topology=true max_brightness=true default_trigger=true"'
    $rollbackHealthInsertion = @'
  if [[ "$GENERATION" -ge 16 ]]; then
    sudo dmesg >"$BACKUP_DIR/dmesg-after-trial.txt" 2>/dev/null || fail "dmesg_post_trial_unavailable" 77
    if ! delta_lines="$(python3 - "$BACKUP_DIR/dmesg-before-trial.txt" "$BACKUP_DIR/dmesg-after-trial.txt" "$BACKUP_DIR/dmesg-trial-delta.txt" <<'PY'
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
        raise SystemExit(79)

delta = after[overlap:]
delta_path.write_text("\n".join(delta) + ("\n" if delta else ""), encoding="utf-8")
print(len(delta))
PY
)"; then
      fail "dmesg_trial_window_unresolved" 79
    fi
    [[ "$delta_lines" =~ ^[0-9]+$ ]] || fail "dmesg_delta_count_invalid:$delta_lines" 80
    fault_pattern='BUG:|WARNING:|Oops:|kernel panic|Call Trace:|KASAN:|UBSAN:|general protection fault|use-after-free|refcount_t: underflow|scheduling while atomic|sleeping function called from invalid context'
    fault_count="$(grep -Eic "$fault_pattern" "$BACKUP_DIR/dmesg-trial-delta.txt" || true)"
    [[ "$fault_count" -eq 0 ]] || fail "kernel_fault_signature_after_candidate_lifecycle:$fault_count" 81
    echo "AURUM_PI4_DRIVER_KERNEL_HEALTH status=passed new_fault_signatures=0 dmesg_delta_lines=$delta_lines ring_buffer_overlap=verified"
  fi
'@
    $rollbackHealthInsertion = $rollbackHealthInsertion.Replace("`r`n", "`n").Replace("`r", "`n")
    if (-not $controlledTrial.Contains($rollbackHealthAnchor)) {
        throw 'Could not locate the generation-15 rollback parity anchor for generation 16.'
    }
    $controlledTrial = $controlledTrial.Replace($rollbackHealthAnchor, $rollbackHealthAnchor + "`n" + $rollbackHealthInsertion)

    Write-Host "AURUM_PI4_DRIVER_GEN16 reference=kernel-fault-free-driver-lifecycle source=ring-safe-dmesg-overlap bounded=true rollback_inherited=true fault_signatures_required_zero=true"
}
