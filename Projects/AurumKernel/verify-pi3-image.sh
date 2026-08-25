#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
VERSION=${AURUM_KERNEL_VERSION:-0.02}
IMAGE_REVISION=${AURUM_PI3_IMAGE_REVISION:-$VERSION}
BUNDLE=${AURUM_PI3_KERNEL_BUNDLE:-$REPO_ROOT/dist/Aurum-Pi3-Kernel-v${VERSION}-arm64}
BUILD_ROOT=${AURUM_PI3_IMAGE_WORK_ROOT:-$HOME/.cache/aurum-pi3-image-v${IMAGE_REVISION}}
RAW_IMG=${AURUM_PI3_RAW_IMAGE:-$BUILD_ROOT/Aurum-Pi3-Kernel-Trial-v${IMAGE_REVISION}-arm64.img}
RECEIPT=${AURUM_PI3_IMAGE_VERIFY_RECEIPT:-$REPO_ROOT/dist/Aurum-Pi3-Kernel-Trial-v${IMAGE_REVISION}-arm64.verify.json}
QPU_CANDIDATE=${AURUM_PI3_QPU_CANDIDATE:-}
QPU_STATUS=${AURUM_PI3_QPU_STATUS:-}
QPU_BRANCH_STATE=${AURUM_PI3_QPU_BRANCH_STATE:-}
QPU_ENABLED=0

case "$IMAGE_REVISION" in
  *[!A-Za-z0-9._-]*|'') echo "AURUM_PI3_IMAGE_REVISION is invalid." >&2; exit 2 ;;
esac

if [ "$(id -u)" -ne 0 ]; then
  echo "verify-pi3-image.sh must run as root for read-only loop mounts." >&2
  exit 2
fi
for tool in cmp grep losetup mount mountpoint python3 sha256sum umount udevadm; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "$tool is required." >&2
    exit 2
  fi
done

BUILD_ROOT=$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$BUILD_ROOT")
RAW_IMG=$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$RAW_IMG")
RECEIPT=$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$RECEIPT")
python3 - "$BUILD_ROOT" "$RAW_IMG" "$RECEIPT" "$REPO_ROOT" <<'PY'
from pathlib import Path
import sys

build, raw, receipt, repo = (Path(value).resolve() for value in sys.argv[1:])
cache = (Path.home() / ".cache").resolve()
dist = (repo / "dist").resolve()
if cache not in build.parents or build not in raw.parents:
    raise SystemExit(f"Refusing raw-image verification outside the root cache: {raw}")
if dist not in receipt.parents:
    raise SystemExit(f"Refusing verification receipt outside repository dist: {receipt}")
PY

test -s "$RAW_IMG"
test -s "$BUNDLE/kernel8-aurum.img"
test -s "$BUNDLE/kernel-release.txt"
if [ -n "$QPU_CANDIDATE$QPU_STATUS$QPU_BRANCH_STATE" ]; then
  if [ -z "$QPU_CANDIDATE" ] || [ -z "$QPU_STATUS" ] || [ -z "$QPU_BRANCH_STATE" ]; then
    echo "QPU verification requires candidate, status, and branch-state paths together." >&2
    exit 2
  fi
  for artifact in "$QPU_CANDIDATE" "$QPU_STATUS" "$QPU_BRANCH_STATE" \
    "$SCRIPT_DIR/pi3_future_branch_qpu_run.py"; do
    test -s "$artifact"
  done
  python3 - "$SCRIPT_DIR/pi3_future_branch_qpu_run.py" \
    "$QPU_CANDIDATE" "$QPU_STATUS" "$QPU_BRANCH_STATE" <<'PY'
import importlib.util
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location("aurum_pi3_qpu_verify", sys.argv[1])
if spec is None or spec.loader is None:
    raise SystemExit("cannot load the Pi 3 QPU evidence gate")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.validate_qpu_evidence(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
PY
  QPU_ENABLED=1
fi
ROOT_MNT="$BUILD_ROOT/verify-root"
BOOT_MNT="$BUILD_ROOT/verify-boot"
rm -rf -- "$ROOT_MNT" "$BOOT_MNT"
mkdir -p "$ROOT_MNT" "$BOOT_MNT"

LOOP_DEV=
cleanup() {
  set +e
  if mountpoint -q "$BOOT_MNT" 2>/dev/null; then umount "$BOOT_MNT"; fi
  if mountpoint -q "$ROOT_MNT" 2>/dev/null; then umount "$ROOT_MNT"; fi
  if [ -n "$LOOP_DEV" ]; then losetup -d "$LOOP_DEV" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

LOOP_DEV=$(losetup --find --show --partscan --read-only "$RAW_IMG")
udevadm settle
test -b "${LOOP_DEV}p1"
test -b "${LOOP_DEV}p2"
mount -o ro "${LOOP_DEV}p2" "$ROOT_MNT"
mount -o ro "${LOOP_DEV}p1" "$BOOT_MNT"

cmp -s "$BUNDLE/kernel8-aurum.img" "$BOOT_MNT/kernel8-aurum.img"
grep -F 'kernel=kernel8-aurum.img' "$BOOT_MNT/config.txt"
grep -F 'arm_64bit=1' "$BOOT_MNT/config.txt"
grep -F 'enable_uart=1' "$BOOT_MNT/config.txt"
grep -F 'console=serial0,115200' "$BOOT_MNT/cmdline.txt"
grep -F 'aurum.pi3_kernel=1' "$BOOT_MNT/cmdline.txt"
test -s "$BOOT_MNT/aurum-stock/config.txt"
test -s "$BOOT_MNT/aurum-stock/cmdline.txt"
test -s "$BOOT_MNT/AURUM-RECOVERY.txt"
for board in bcm2710-rpi-3-b.dtb bcm2710-rpi-3-b-plus.dtb bcm2710-rpi-3-a-plus.dtb; do
  cmp -s "$BUNDLE/dtbs/$board" "$BOOT_MNT/$board"
done
KERNEL_RELEASE=$(cat "$BUNDLE/kernel-release.txt")
test -L "$ROOT_MNT/lib"
test "$(readlink "$ROOT_MNT/lib")" = "usr/lib"
test -e "$ROOT_MNT/lib/ld-linux-aarch64.so.1"
test -d "$ROOT_MNT/lib/modules/$KERNEL_RELEASE"
test -x "$ROOT_MNT/usr/local/sbin/aurum-pi3-kernel-ready"
test -L "$ROOT_MNT/etc/systemd/system/multi-user.target.wants/aurum-pi3-kernel-ready.service"
grep -F 'ConditionKernelCommandLine=aurum.pi3_kernel=1' \
  "$ROOT_MNT/etc/systemd/system/aurum-pi3-kernel-ready.service"
if [ "$QPU_ENABLED" -eq 1 ]; then
  grep -F 'aurum.pi3_future_branch=1' "$BOOT_MNT/cmdline.txt"
  cmp -s "$QPU_CANDIDATE" "$ROOT_MNT/etc/aurum/future-branch-qpu.json"
  cmp -s "$QPU_STATUS" "$ROOT_MNT/etc/aurum/qpu-status.json"
  cmp -s "$QPU_BRANCH_STATE" "$ROOT_MNT/etc/aurum/future-branch-state.json"
  cmp -s "$QPU_CANDIDATE" "$BOOT_MNT/aurum-evidence/future-branch-qpu.json"
  cmp -s "$QPU_STATUS" "$BOOT_MNT/aurum-evidence/qpu-status.json"
  cmp -s "$QPU_BRANCH_STATE" "$BOOT_MNT/aurum-evidence/future-branch-state.json"
  test -x "$ROOT_MNT/usr/local/lib/aurum-futurebranch/pi3_future_branch_qpu_run.py"
  test -s "$ROOT_MNT/usr/local/lib/aurum-futurebranch/pi3_physical_probe.py"
  test -L "$ROOT_MNT/etc/systemd/system/multi-user.target.wants/aurum-pi3-future-branch-qpu.service"
  grep -F 'ConditionKernelCommandLine=aurum.pi3_future_branch=1' \
    "$ROOT_MNT/etc/systemd/system/aurum-pi3-future-branch-qpu.service"
  grep -F 'StandardOutput=journal+console' \
    "$ROOT_MNT/etc/systemd/system/aurum-pi3-future-branch-qpu.service"
fi

RAW_SHA=$(sha256sum "$RAW_IMG" | awk '{print $1}')
KERNEL_SHA=$(sha256sum "$BUNDLE/kernel8-aurum.img" | awk '{print $1}')
umount "$BOOT_MNT"
umount "$ROOT_MNT"
losetup -d "$LOOP_DEV"
LOOP_DEV=

export AURUM_VERIFY_RECEIPT="$RECEIPT"
export AURUM_VERIFY_RAW_SHA="$RAW_SHA"
export AURUM_VERIFY_KERNEL_SHA="$KERNEL_SHA"
export AURUM_VERIFY_KERNEL_RELEASE="$KERNEL_RELEASE"
export AURUM_VERIFY_IMAGE_REVISION="$IMAGE_REVISION"
export AURUM_VERIFY_QPU_ENABLED="$QPU_ENABLED"
python3 - <<'PY'
import json
import os
from pathlib import Path

payload = {
    "schema": "aurum-pi3-trial-image-verification-v1",
    "state": "success",
    "image_revision": os.environ["AURUM_VERIFY_IMAGE_REVISION"],
    "carrier": "read-only-loop-mount",
    "raw_image_sha256": os.environ["AURUM_VERIFY_RAW_SHA"],
    "kernel_sha256": os.environ["AURUM_VERIFY_KERNEL_SHA"],
    "kernel_release": os.environ["AURUM_VERIFY_KERNEL_RELEASE"],
    "verified": {
        "boot_configuration": True,
        "kernel_content": True,
        "device_trees": True,
        "matching_modules": True,
        "merged_usr_dynamic_loader": True,
        "physical_readiness_service": True,
        "stock_recovery_files": True,
    },
    "physical_pi3_boot": False,
}
if os.environ["AURUM_VERIFY_QPU_ENABLED"] == "1":
    payload["verified"]["future_branch_qpu_evidence"] = True
    payload["verified"]["future_branch_physical_collapse_service"] = True
Path(os.environ["AURUM_VERIFY_RECEIPT"]).write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(json.dumps(payload, sort_keys=True))
PY
printf 'AURUM_PI3_TRIAL_IMAGE_VERIFIED receipt=%s\n' "$RECEIPT"
