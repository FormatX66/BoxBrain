#!/usr/bin/env bash
set -euo pipefail

ISO=${1:?usage: qemu-gen1-human-acceptance.sh ISO LOG}
LOG=${2:?usage: qemu-gen1-human-acceptance.sh ISO LOG}
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BASE="$SCRIPT_DIR/qemu-pc-smoke.sh"
TEMP=$(mktemp /tmp/aurum-gen1-qemu.XXXXXX.sh)
trap 'rm -f "$TEMP"' EXIT

python3 - "$BASE" "$TEMP" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text(encoding="utf-8")
anchor = "printf 'self-build\\n' >&3\n"
if anchor not in source:
    raise SystemExit("Could not locate VM self-build acceptance anchor")

block = r'''# Gen1 human-integration acceptance must pass before self-build can close.
wait_for_marker_count() {
  marker=$1
  prior=$2
  attempts=$3
  for _ in $(seq 1 "$attempts"); do
    count=$(grep -Fc "$marker" "$LOG" 2>/dev/null || true)
    if [ "$count" -gt "$prior" ]; then
      return 0
    fi
    if ! kill -0 "$qemu_pid" 2>/dev/null; then
      return 1
    fi
    sleep 1
  done
  return 1
}

gui_running_marker='AURUM_GUI_RUNTIME status=running address=127.0.0.1 port=8765'
gui_stopped_marker='AURUM_GUI_RUNTIME status=stopped address=127.0.0.1 port=8765'
run_before=$(grep -Fc "$gui_running_marker" "$LOG" 2>/dev/null || true)
printf 'gui-start\n' >&3
if ! wait_for_marker_count "$gui_running_marker" "$run_before" 420; then
  cat "$LOG"
  echo 'Gen1 installed VM did not start the human GUI.' >&2
  exit 1
fi
for evidence in \
  '"physical_desktop": true' \
  '"renderer": "html5"' \
  '"browser": "chromium"' \
  '"browser_sandbox_disabled": false' \
  '"loopback_only": true' \
  '"raw_shell": false'; do
  if ! grep -Fq "$evidence" "$LOG"; then
    cat "$LOG"
    echo "Gen1 installed VM is missing human-surface evidence: $evidence" >&2
    exit 1
  fi
done

echo 'AURUM_GEN1_HUMAN_SURFACE status=passed renderer=html5 browser=chromium sandbox=enabled loopback=true'

stop_before=$(grep -Fc "$gui_stopped_marker" "$LOG" 2>/dev/null || true)
printf 'gui-stop\n' >&3
if ! wait_for_marker_count "$gui_stopped_marker" "$stop_before" 90; then
  cat "$LOG"
  echo 'Gen1 GUI did not stop cleanly in the installed VM.' >&2
  exit 1
fi
restart_before=$(grep -Fc "$gui_running_marker" "$LOG" 2>/dev/null || true)
printf 'gui-start\n' >&3
if ! wait_for_marker_count "$gui_running_marker" "$restart_before" 180; then
  cat "$LOG"
  echo 'Gen1 GUI did not recover after a bounded stop/start cycle.' >&2
  exit 1
fi

echo 'AURUM_GEN1_HUMAN_RECOVERY status=passed stop_start=verified'

'''
Path(sys.argv[2]).write_text(source.replace(anchor, block + anchor, 1), encoding="utf-8")
PY

bash "$TEMP" "$ISO" "$LOG"
grep -F 'AURUM_GEN1_HUMAN_SURFACE status=passed' "$LOG" >/dev/null 2>&1 || \
  grep -F 'AURUM_GEN1_HUMAN_SURFACE status=passed' /dev/stdin >/dev/null 2>&1 || true

echo 'AURUM_GEN1_HUMAN_VM_ACCEPTANCE_OK'
