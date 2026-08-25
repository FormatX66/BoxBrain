#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
VERSION=${AURUM_KERNEL_VERSION:-0.02}
BUNDLE=${AURUM_KERNEL_BUNDLE:-$REPO_ROOT/dist/Aurum-Kernel-v${VERSION}-x86_64}
TIMEOUT_SECONDS=${AURUM_BOOT_TIMEOUT:-60}
LOG=${AURUM_BOOT_LOG:-$BUNDLE/qemu-boot.log}
RECEIPT=${AURUM_BOOT_RECEIPT:-$BUNDLE/boot-test-receipt.json}

for tool in qemu-system-x86_64 timeout sha256sum python3; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "$tool is required." >&2
    exit 2
  fi
done
for artifact in bzImage initramfs.cpio.gz SHA256SUMS; do
  if [ ! -s "$BUNDLE/$artifact" ]; then
    echo "Missing kernel artifact: $BUNDLE/$artifact" >&2
    exit 2
  fi
done

(
  cd "$BUNDLE"
  sha256sum -c SHA256SUMS
)

set +e
timeout "$TIMEOUT_SECONDS" qemu-system-x86_64 \
  -machine q35,accel=tcg \
  -cpu qemu64 \
  -m 768 \
  -smp 2 \
  -kernel "$BUNDLE/bzImage" \
  -initrd "$BUNDLE/initramfs.cpio.gz" \
  -append 'console=ttyS0 rdinit=/init panic=-1' \
  -display none \
  -serial stdio \
  -monitor none \
  -no-reboot \
  > "$LOG" 2>&1
QEMU_STATUS=$?
set -e

READY_MARKER="AURUM_KERNEL_READY version=$VERSION arch=x86_64"
grep -F "$READY_MARKER" "$LOG"
grep -F 'selftest=ok' "$LOG"
if [ "$QEMU_STATUS" -ne 0 ] && [ "$QEMU_STATUS" -ne 124 ]; then
  echo "QEMU exited unexpectedly with status $QEMU_STATUS" >&2
  exit "$QEMU_STATUS"
fi

export AURUM_RECEIPT_BUNDLE="$BUNDLE"
export AURUM_RECEIPT_LOG="$LOG"
export AURUM_RECEIPT_PATH="$RECEIPT"
export AURUM_RECEIPT_STATUS="$QEMU_STATUS"
export AURUM_RECEIPT_MARKER="$READY_MARKER"
python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path
import subprocess

bundle = Path(os.environ["AURUM_RECEIPT_BUNDLE"]).resolve()
log = Path(os.environ["AURUM_RECEIPT_LOG"]).resolve()
receipt = Path(os.environ["AURUM_RECEIPT_PATH"]).resolve()

def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()

qemu_version = subprocess.run(
    ("qemu-system-x86_64", "--version"),
    check=True,
    capture_output=True,
    text=True,
).stdout.splitlines()[0]
payload = {
    "schema": "aurum-kernel-boot-test-v1",
    "state": "success",
    "carrier": "qemu-system-x86_64-tcg",
    "qemu_version": qemu_version,
    "qemu_exit_status": int(os.environ["AURUM_RECEIPT_STATUS"]),
    "expected_timeout_exit": int(os.environ["AURUM_RECEIPT_STATUS"]) == 124,
    "kernel_sha256": digest(bundle / "bzImage"),
    "initramfs_sha256": digest(bundle / "initramfs.cpio.gz"),
    "log_sha256": digest(log),
    "markers": [os.environ["AURUM_RECEIPT_MARKER"], "selftest=ok"],
}
receipt.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(payload, sort_keys=True))
PY

printf 'AURUM_KERNEL_BOOT_VERIFIED receipt=%s\n' "$RECEIPT"
