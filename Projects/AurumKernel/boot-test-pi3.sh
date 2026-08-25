#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
VERSION=${AURUM_KERNEL_VERSION:-0.02}
BUNDLE=${AURUM_PI3_KERNEL_BUNDLE:-$REPO_ROOT/dist/Aurum-Pi3-Kernel-v${VERSION}-arm64}
TIMEOUT_SECONDS=${AURUM_BOOT_TIMEOUT:-90}
LOG=${AURUM_BOOT_LOG:-$BUNDLE/qemu-pi3-boot.log}
RECEIPT=${AURUM_BOOT_RECEIPT:-$BUNDLE/boot-test-receipt.json}
DTB="$BUNDLE/dtbs/bcm2710-rpi-3-b.dtb"

for tool in qemu-system-aarch64 timeout sha256sum python3; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "$tool is required." >&2
    exit 2
  fi
done
for artifact in kernel8-aurum.img pi3-initramfs.cpio.gz SHA256SUMS; do
  if [ ! -s "$BUNDLE/$artifact" ]; then
    echo "Missing Pi 3 kernel artifact: $BUNDLE/$artifact" >&2
    exit 2
  fi
done
test -s "$DTB"
(
  cd "$BUNDLE"
  sha256sum -c SHA256SUMS
)

set +e
timeout "$TIMEOUT_SECONDS" qemu-system-aarch64 \
  -machine raspi3b \
  -cpu cortex-a53 \
  -m 1G \
  -smp 4 \
  -kernel "$BUNDLE/kernel8-aurum.img" \
  -dtb "$DTB" \
  -initrd "$BUNDLE/pi3-initramfs.cpio.gz" \
  -append 'console=ttyAMA1,115200 rdinit=/init panic=-1' \
  -display none \
  -serial stdio \
  -monitor none \
  -no-reboot \
  > "$LOG" 2>&1
QEMU_STATUS=$?
set -e

READY_MARKER="AURUM_PI3_KERNEL_READY version=$VERSION arch=arm64"
grep -F "$READY_MARKER" "$LOG"
grep -F 'selftest=ok' "$LOG"
if [ "$QEMU_STATUS" -ne 0 ] && [ "$QEMU_STATUS" -ne 124 ]; then
  echo "QEMU exited unexpectedly with status $QEMU_STATUS" >&2
  exit "$QEMU_STATUS"
fi

export AURUM_RECEIPT_BUNDLE="$BUNDLE"
export AURUM_RECEIPT_DTB="$DTB"
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
dtb = Path(os.environ["AURUM_RECEIPT_DTB"]).resolve()
log = Path(os.environ["AURUM_RECEIPT_LOG"]).resolve()
receipt = Path(os.environ["AURUM_RECEIPT_PATH"]).resolve()

def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()

payload = {
    "schema": "aurum-pi3-kernel-boot-test-v1",
    "state": "success",
    "carrier": "qemu-system-aarch64-raspi3b",
    "qemu_version": subprocess.run(
        ("qemu-system-aarch64", "--version"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()[0],
    "qemu_exit_status": int(os.environ["AURUM_RECEIPT_STATUS"]),
    "expected_timeout_exit": int(os.environ["AURUM_RECEIPT_STATUS"]) == 124,
    "kernel_sha256": digest(bundle / "kernel8-aurum.img"),
    "initramfs_sha256": digest(bundle / "pi3-initramfs.cpio.gz"),
    "dtb_sha256": digest(dtb),
    "log_sha256": digest(log),
    "markers": [os.environ["AURUM_RECEIPT_MARKER"], "selftest=ok"],
    "physical_hardware_evidence": False,
}
receipt.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(payload, sort_keys=True))
PY

printf 'AURUM_PI3_KERNEL_BOOT_VERIFIED receipt=%s\n' "$RECEIPT"
