#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
VERSION=${AURUM_KERNEL_VERSION:-0.02}
IMAGE_REVISION=${AURUM_PI3_IMAGE_REVISION:-$VERSION}
BUNDLE=${AURUM_PI3_KERNEL_BUNDLE:-$REPO_ROOT/dist/Aurum-Pi3-Kernel-v${VERSION}-arm64}
BUILD_ROOT=${AURUM_PI3_IMAGE_WORK_ROOT:-$HOME/.cache/aurum-pi3-image-v${IMAGE_REVISION}}
BASE_CACHE=${AURUM_PI3_BASE_CACHE:-$HOME/.cache/aurum-pi3-base}
DIST=${AURUM_PI3_IMAGE_DIST:-$REPO_ROOT/dist}
IMAGE_STEM="Aurum-Pi3-Kernel-Trial-v${IMAGE_REVISION}-arm64"
RAW_IMG="$BUILD_ROOT/$IMAGE_STEM.img"
OUT_XZ="$DIST/$IMAGE_STEM.img.xz"
OUT_SHA="$OUT_XZ.sha256"
OUT_MANIFEST="$DIST/$IMAGE_STEM.manifest.json"
OUT_PARTITIONS="$DIST/$IMAGE_STEM.partitions.txt"
BASE_XZ="$BASE_CACHE/2026-06-18-raspios-trixie-arm64-lite.img.xz"
BASE_URL=https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-2026-06-19/2026-06-18-raspios-trixie-arm64-lite.img.xz
BASE_SHA256=acff736ca7945e3b305f07cda4abdb870910e12634991da69783611756e381b3
QPU_CANDIDATE=${AURUM_PI3_QPU_CANDIDATE:-}
QPU_STATUS=${AURUM_PI3_QPU_STATUS:-}
QPU_BRANCH_STATE=${AURUM_PI3_QPU_BRANCH_STATE:-}
QPU_ENABLED=0

case "$IMAGE_REVISION" in
  *[!A-Za-z0-9._-]*|'') echo "AURUM_PI3_IMAGE_REVISION is invalid." >&2; exit 2 ;;
esac

if [ "$(id -u)" -ne 0 ]; then
  echo "prepare-pi3-image.sh must run as root for loop and mount operations." >&2
  exit 2
fi
for tool in curl xz sha256sum losetup mount umount mountpoint udevadm \
  sfdisk e2fsck python3 tar; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "$tool is required." >&2
    exit 2
  fi
done
for artifact in kernel8-aurum.img modules.tar.gz kernel-release.txt \
  source-commit.txt SHA256SUMS boot-test-receipt.json; do
  if [ ! -s "$BUNDLE/$artifact" ]; then
    echo "Missing boot-verified Pi 3 bundle artifact: $BUNDLE/$artifact" >&2
    exit 2
  fi
done
(
  cd "$BUNDLE"
  sha256sum -c SHA256SUMS
)
python3 - "$BUNDLE/boot-test-receipt.json" "$BUNDLE/kernel8-aurum.img" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

receipt = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if receipt.get("schema") != "aurum-pi3-kernel-boot-test-v1":
    raise SystemExit("Pi 3 kernel boot receipt schema mismatch")
if receipt.get("state") != "success":
    raise SystemExit("Pi 3 kernel bundle has no successful boot receipt")
kernel_hash = hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()
if receipt.get("kernel_sha256") != kernel_hash:
    raise SystemExit("Pi 3 boot receipt does not bind the supplied kernel")
PY

if [ -n "$QPU_CANDIDATE$QPU_STATUS$QPU_BRANCH_STATE" ]; then
  if [ -z "$QPU_CANDIDATE" ] || [ -z "$QPU_STATUS" ] || [ -z "$QPU_BRANCH_STATE" ]; then
    echo "QPU evidence requires candidate, status, and branch-state paths together." >&2
    exit 2
  fi
  for artifact in "$QPU_CANDIDATE" "$QPU_STATUS" "$QPU_BRANCH_STATE" \
    "$SCRIPT_DIR/pi3_future_branch_qpu_run.py"; do
    if [ ! -s "$artifact" ]; then
      echo "Missing Pi 3 FutureBranch QPU artifact: $artifact" >&2
      exit 2
    fi
  done
  python3 - "$SCRIPT_DIR/pi3_future_branch_qpu_run.py" \
    "$QPU_CANDIDATE" "$QPU_STATUS" "$QPU_BRANCH_STATE" <<'PY'
import importlib.util
import json
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location("aurum_pi3_qpu_gate", sys.argv[1])
if spec is None or spec.loader is None:
    raise SystemExit("cannot load the Pi 3 QPU evidence gate")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
result = module.validate_qpu_evidence(
    Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
)
print(json.dumps(result, sort_keys=True))
PY
  QPU_ENABLED=1
fi

BUILD_ROOT=$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$BUILD_ROOT")
BASE_CACHE=$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$BASE_CACHE")
DIST=$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$DIST")
python3 - "$BUILD_ROOT" "$BASE_CACHE" "$DIST" "$REPO_ROOT" <<'PY'
from pathlib import Path
import sys

build, cache, dist, repo = (Path(value).resolve() for value in sys.argv[1:])
user_cache = (Path.home() / ".cache").resolve()
dist_root = (repo / "dist").resolve()
for label, path in (("build", build), ("base cache", cache)):
    if user_cache not in path.parents:
        raise SystemExit(f"Refusing {label} outside the user cache: {path}")
if dist != dist_root:
    raise SystemExit(f"Refusing image output outside the repository dist root: {dist}")
if build == cache or build in cache.parents or cache in build.parents:
    raise SystemExit(f"Refusing overlapping build and base-cache roots: {build} / {cache}")
PY

rm -rf -- "$BUILD_ROOT"
mkdir -p "$BUILD_ROOT" "$BASE_CACHE" "$DIST"
rm -f -- "$OUT_XZ" "$OUT_SHA" "$OUT_MANIFEST" "$OUT_PARTITIONS"
if [ ! -s "$BASE_XZ" ] || ! printf '%s  %s\n' "$BASE_SHA256" "$BASE_XZ" | sha256sum -c - >/dev/null 2>&1; then
  rm -f -- "$BASE_XZ"
  curl -L --fail --retry 5 --retry-delay 2 -o "$BASE_XZ" "$BASE_URL"
fi
printf '%s  %s\n' "$BASE_SHA256" "$BASE_XZ" | sha256sum -c -
xz -dc "$BASE_XZ" > "$RAW_IMG"

LOOP_DEV=
ROOT_MNT="$BUILD_ROOT/root"
BOOT_MNT="$ROOT_MNT/boot/firmware"
cleanup() {
  set +e
  if mountpoint -q "$BOOT_MNT" 2>/dev/null; then umount "$BOOT_MNT"; fi
  if mountpoint -q "$ROOT_MNT" 2>/dev/null; then umount "$ROOT_MNT"; fi
  if [ -n "$LOOP_DEV" ]; then losetup -d "$LOOP_DEV" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

LOOP_DEV=$(losetup --find --show --partscan "$RAW_IMG")
udevadm settle
ROOT_PART="${LOOP_DEV}p2"
BOOT_PART="${LOOP_DEV}p1"
for _ in $(seq 1 20); do
  [ -b "$ROOT_PART" ] && [ -b "$BOOT_PART" ] && break
  sleep 1
  udevadm settle
done
test -b "$ROOT_PART"
test -b "$BOOT_PART"
mkdir -p "$ROOT_MNT"
mount "$ROOT_PART" "$ROOT_MNT"
mkdir -p "$BOOT_MNT"
mount "$BOOT_PART" "$BOOT_MNT"

STOCK="$BOOT_MNT/aurum-stock"
mkdir -p "$STOCK/dtbs"
cp "$BOOT_MNT/config.txt" "$STOCK/config.txt"
cp "$BOOT_MNT/cmdline.txt" "$STOCK/cmdline.txt"
if [ -s "$BOOT_MNT/kernel8.img" ]; then
  cp "$BOOT_MNT/kernel8.img" "$STOCK/kernel8.img"
fi
for board in bcm2710-rpi-3-b.dtb bcm2710-rpi-3-b-plus.dtb bcm2710-rpi-3-a-plus.dtb; do
  if [ -s "$BOOT_MNT/$board" ]; then cp "$BOOT_MNT/$board" "$STOCK/dtbs/$board"; fi
  cp "$BUNDLE/dtbs/$board" "$BOOT_MNT/$board"
done
cp "$BUNDLE/kernel8-aurum.img" "$BOOT_MNT/kernel8-aurum.img"
cp "$BUNDLE/overlays/"*.dtbo "$BOOT_MNT/overlays/"
if [ -f "$BUNDLE/overlays/README" ]; then
  cp "$BUNDLE/overlays/README" "$BOOT_MNT/overlays/README"
fi
KERNEL_RELEASE=$(cat "$BUNDLE/kernel-release.txt")
if [ ! -L "$ROOT_MNT/lib" ] || [ "$(readlink "$ROOT_MNT/lib")" != "usr/lib" ]; then
  echo "Refusing module install because the base image lacks /lib -> usr/lib." >&2
  exit 1
fi
MODULE_EXTRACT="$BUILD_ROOT/module-extract"
rm -rf -- "$MODULE_EXTRACT"
mkdir -p "$MODULE_EXTRACT"
tar -C "$MODULE_EXTRACT" -xzf "$BUNDLE/modules.tar.gz"
test -d "$MODULE_EXTRACT/lib/modules/$KERNEL_RELEASE"
install -d -m 0755 "$ROOT_MNT/usr/lib/modules"
cp -a "$MODULE_EXTRACT/lib/modules/." "$ROOT_MNT/usr/lib/modules/"
test -L "$ROOT_MNT/lib"
test -e "$ROOT_MNT/lib/ld-linux-aarch64.so.1"
test -d "$ROOT_MNT/lib/modules/$KERNEL_RELEASE"

cat >> "$BOOT_MNT/config.txt" <<EOF

# Aurum Pi 3 self-kernel trial image v$IMAGE_REVISION (kernel v$VERSION)
[pi3]
arm_64bit=1
kernel=kernel8-aurum.img
enable_uart=1
[all]
EOF
CMDLINE=$(tr -d '\r\n' < "$BOOT_MNT/cmdline.txt")
case " $CMDLINE " in
  *" console=serial0,115200 "*) : ;;
  *) CMDLINE="$CMDLINE console=serial0,115200" ;;
esac
case " $CMDLINE " in
  *" aurum.pi3_kernel=1 "*) : ;;
  *) CMDLINE="$CMDLINE aurum.pi3_kernel=1" ;;
esac
if [ "$QPU_ENABLED" -eq 1 ]; then
  case " $CMDLINE " in
    *" aurum.pi3_future_branch=1 "*) : ;;
    *) CMDLINE="$CMDLINE aurum.pi3_future_branch=1" ;;
  esac
fi
printf '%s\n' "$CMDLINE" > "$BOOT_MNT/cmdline.txt"

install -d -m 0755 "$ROOT_MNT/etc/aurum" "$ROOT_MNT/usr/local/sbin"
cp "$BUNDLE/kernel-release.txt" "$ROOT_MNT/etc/aurum/kernel-release"
cat > "$ROOT_MNT/usr/local/sbin/aurum-pi3-kernel-ready" <<'EOF'
#!/bin/sh
set -eu
EXPECTED=$(cat /etc/aurum/kernel-release)
ACTUAL=$(uname -r)
if [ "$ACTUAL" != "$EXPECTED" ]; then
  echo "AURUM_PI3_KERNEL_MISMATCH expected=$EXPECTED actual=$ACTUAL" >/dev/console
  exit 1
fi
MESSAGE="AURUM_PI3_PHYSICAL_READY kernel=$ACTUAL arch=$(uname -m) selftest=ok"
echo "$MESSAGE" >/dev/console
if [ -w /dev/serial0 ]; then echo "$MESSAGE" >/dev/serial0; fi
install -d -m 0755 /run/aurum
printf '%s\n' "$MESSAGE" > /run/aurum/pi3-kernel-ready
EOF
chmod 0755 "$ROOT_MNT/usr/local/sbin/aurum-pi3-kernel-ready"
cat > "$ROOT_MNT/etc/systemd/system/aurum-pi3-kernel-ready.service" <<'EOF'
[Unit]
Description=Aurum Pi 3 self-kernel readiness proof
After=local-fs.target systemd-modules-load.service
ConditionKernelCommandLine=aurum.pi3_kernel=1

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/aurum-pi3-kernel-ready
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
mkdir -p "$ROOT_MNT/etc/systemd/system/multi-user.target.wants"
ln -sfn ../aurum-pi3-kernel-ready.service \
  "$ROOT_MNT/etc/systemd/system/multi-user.target.wants/aurum-pi3-kernel-ready.service"
if [ "$QPU_ENABLED" -eq 1 ]; then
  FUTURE_BRANCH_LIB="$ROOT_MNT/usr/local/lib/aurum-futurebranch"
  install -d -m 0755 "$FUTURE_BRANCH_LIB" "$ROOT_MNT/var/lib/aurum" \
    "$BOOT_MNT/aurum-evidence"
  install -m 0755 "$SCRIPT_DIR/pi3_future_branch_qpu_run.py" \
    "$FUTURE_BRANCH_LIB/pi3_future_branch_qpu_run.py"
  for module in experiment_suite.py pi3_physical_probe.py reality_gap.py gap_stack.py \
    surprise_budget.py human_availability.py unattended_precompute.py execution_route.py; do
    install -m 0644 "$REPO_ROOT/Projects/Aurum/Experiments/$module" \
      "$FUTURE_BRANCH_LIB/$module"
  done
  install -m 0644 "$QPU_CANDIDATE" "$ROOT_MNT/etc/aurum/future-branch-qpu.json"
  install -m 0644 "$QPU_STATUS" "$ROOT_MNT/etc/aurum/qpu-status.json"
  install -m 0644 "$QPU_BRANCH_STATE" "$ROOT_MNT/etc/aurum/future-branch-state.json"
  cp "$QPU_CANDIDATE" "$BOOT_MNT/aurum-evidence/future-branch-qpu.json"
  cp "$QPU_STATUS" "$BOOT_MNT/aurum-evidence/qpu-status.json"
  cp "$QPU_BRANCH_STATE" "$BOOT_MNT/aurum-evidence/future-branch-state.json"
  cat > "$ROOT_MNT/etc/systemd/system/aurum-pi3-future-branch-qpu.service" <<'EOF'
[Unit]
Description=Aurum Pi 3 complete FutureBranch QPU physical collapse
Requires=aurum-pi3-kernel-ready.service
After=aurum-pi3-kernel-ready.service
ConditionKernelCommandLine=aurum.pi3_future_branch=1

[Service]
Type=oneshot
ExecStart=/usr/local/lib/aurum-futurebranch/pi3_future_branch_qpu_run.py
StandardOutput=journal+console
StandardError=journal+console
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
  ln -sfn ../aurum-pi3-future-branch-qpu.service \
    "$ROOT_MNT/etc/systemd/system/multi-user.target.wants/aurum-pi3-future-branch-qpu.service"
fi
printf '%s\n' 'aurum-pi3-kernel' > "$ROOT_MNT/etc/hostname"
cat > "$BOOT_MNT/AURUM-RECOVERY.txt" <<'EOF'
Aurum Pi 3 trial card recovery

Preferred recovery: power off and replace this trial card with the untouched
Last Known Good microSD card.

To make this trial card use its stock kernel again, mount the boot partition,
restore aurum-stock/config.txt and aurum-stock/cmdline.txt, then restore the
three DTB files from aurum-stock/dtbs. The original kernel is preserved as
aurum-stock/kernel8.img.
EOF

sync
umount "$BOOT_MNT"
umount "$ROOT_MNT"
e2fsck -fn "$ROOT_PART"
sfdisk -d "$LOOP_DEV" > "$OUT_PARTITIONS"
losetup -d "$LOOP_DEV"
LOOP_DEV=

RAW_SHA=$(sha256sum "$RAW_IMG" | awk '{print $1}')
RAW_BYTES=$(stat -c '%s' "$RAW_IMG")
XZ_OPT=-3 xz -T0 -c "$RAW_IMG" > "$OUT_XZ"
(
  cd "$DIST"
  sha256sum "$(basename "$OUT_XZ")" > "$(basename "$OUT_SHA")"
)
XZ_SHA=$(sha256sum "$OUT_XZ" | awk '{print $1}')
XZ_BYTES=$(stat -c '%s' "$OUT_XZ")
KERNEL_SHA=$(sha256sum "$BUNDLE/kernel8-aurum.img" | awk '{print $1}')
KERNEL_RELEASE=$(cat "$BUNDLE/kernel-release.txt")
SOURCE_COMMIT=$(cat "$BUNDLE/source-commit.txt")
QPU_CANDIDATE_SHA=
QPU_STATUS_SHA=
QPU_BRANCH_STATE_SHA=
QPU_BACKEND=
QPU_JOB_ID=
if [ "$QPU_ENABLED" -eq 1 ]; then
  QPU_CANDIDATE_SHA=$(sha256sum "$QPU_CANDIDATE" | awk '{print $1}')
  QPU_STATUS_SHA=$(sha256sum "$QPU_STATUS" | awk '{print $1}')
  QPU_BRANCH_STATE_SHA=$(sha256sum "$QPU_BRANCH_STATE" | awk '{print $1}')
  QPU_BACKEND=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["backend"])' "$QPU_STATUS")
  QPU_JOB_ID=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["job_id"])' "$QPU_STATUS")
fi
export AURUM_IMAGE_MANIFEST="$OUT_MANIFEST"
export AURUM_IMAGE_NAME="$(basename "$OUT_XZ")"
export AURUM_IMAGE_XZ_SHA="$XZ_SHA"
export AURUM_IMAGE_XZ_BYTES="$XZ_BYTES"
export AURUM_IMAGE_RAW_SHA="$RAW_SHA"
export AURUM_IMAGE_RAW_BYTES="$RAW_BYTES"
export AURUM_IMAGE_KERNEL_SHA="$KERNEL_SHA"
export AURUM_IMAGE_KERNEL_RELEASE="$KERNEL_RELEASE"
export AURUM_IMAGE_SOURCE_COMMIT="$SOURCE_COMMIT"
export AURUM_IMAGE_REVISION="$IMAGE_REVISION"
export AURUM_IMAGE_BASE_URL="$BASE_URL"
export AURUM_IMAGE_BASE_SHA="$BASE_SHA256"
export AURUM_IMAGE_QPU_ENABLED="$QPU_ENABLED"
export AURUM_IMAGE_QPU_CANDIDATE_SHA="$QPU_CANDIDATE_SHA"
export AURUM_IMAGE_QPU_STATUS_SHA="$QPU_STATUS_SHA"
export AURUM_IMAGE_QPU_BRANCH_STATE_SHA="$QPU_BRANCH_STATE_SHA"
export AURUM_IMAGE_QPU_BACKEND="$QPU_BACKEND"
export AURUM_IMAGE_QPU_JOB_ID="$QPU_JOB_ID"
python3 - <<'PY'
import json
import os
from pathlib import Path

payload = {
    "schema": "aurum-pi3-self-kernel-trial-image-v1",
    "target": "raspberry-pi-3",
    "architecture": "arm64",
    "image_revision": os.environ["AURUM_IMAGE_REVISION"],
    "media": "microSD/raw-disk-image",
    "kernel": {
        "release": os.environ["AURUM_IMAGE_KERNEL_RELEASE"],
        "sha256": os.environ["AURUM_IMAGE_KERNEL_SHA"],
        "source_commit": os.environ["AURUM_IMAGE_SOURCE_COMMIT"],
        "qemu_boot_verified": True,
    },
    "base": {
        "name": "Raspberry Pi OS Lite 64-bit",
        "url": os.environ["AURUM_IMAGE_BASE_URL"],
        "sha256": os.environ["AURUM_IMAGE_BASE_SHA"],
    },
    "output": {
        "image": os.environ["AURUM_IMAGE_NAME"],
        "compressed_sha256": os.environ["AURUM_IMAGE_XZ_SHA"],
        "compressed_bytes": int(os.environ["AURUM_IMAGE_XZ_BYTES"]),
        "raw_sha256": os.environ["AURUM_IMAGE_RAW_SHA"],
        "raw_bytes": int(os.environ["AURUM_IMAGE_RAW_BYTES"]),
    },
    "verification": {
        "base_checksum": True,
        "filesystem_check": True,
        "merged_usr_dynamic_loader": True,
        "partition_structure": True,
        "stock_kernel_preserved": True,
        "physical_pi3_boot": False,
    },
}
if os.environ["AURUM_IMAGE_QPU_ENABLED"] == "1":
    payload["future_branch_qpu"] = {
        "provider": "ibm_quantum",
        "backend": os.environ["AURUM_IMAGE_QPU_BACKEND"],
        "job_id": os.environ["AURUM_IMAGE_QPU_JOB_ID"],
        "shots": 256,
        "candidate_sha256": os.environ["AURUM_IMAGE_QPU_CANDIDATE_SHA"],
        "result_sha256": os.environ["AURUM_IMAGE_QPU_STATUS_SHA"],
        "branch_state_sha256": os.environ["AURUM_IMAGE_QPU_BRANCH_STATE_SHA"],
        "physical_collapse_pending": True,
        "secret_free": True,
    }
Path(os.environ["AURUM_IMAGE_MANIFEST"]).write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(json.dumps(payload, sort_keys=True))
PY
xz -t "$OUT_XZ"
(
  cd "$DIST"
  sha256sum -c "$(basename "$OUT_SHA")"
)
AURUM_KERNEL_VERSION="$VERSION" \
AURUM_PI3_IMAGE_REVISION="$IMAGE_REVISION" \
AURUM_PI3_KERNEL_BUNDLE="$BUNDLE" \
AURUM_PI3_IMAGE_WORK_ROOT="$BUILD_ROOT" \
AURUM_PI3_RAW_IMAGE="$RAW_IMG" \
AURUM_PI3_QPU_CANDIDATE="$QPU_CANDIDATE" \
AURUM_PI3_QPU_STATUS="$QPU_STATUS" \
AURUM_PI3_QPU_BRANCH_STATE="$QPU_BRANCH_STATE" \
  sh "$SCRIPT_DIR/verify-pi3-image.sh"
printf 'AURUM_PI3_TRIAL_IMAGE_READY image=%s manifest=%s\n' "$OUT_XZ" "$OUT_MANIFEST"
