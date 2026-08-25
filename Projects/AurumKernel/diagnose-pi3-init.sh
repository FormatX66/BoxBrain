#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
VERSION=${AURUM_KERNEL_VERSION:-0.02}
IMAGE_REVISION=${AURUM_PI3_IMAGE_REVISION:-$VERSION}
BUILD_ROOT=${AURUM_PI3_IMAGE_WORK_ROOT:-$HOME/.cache/aurum-pi3-image-v${IMAGE_REVISION}}
RAW_IMG=${AURUM_PI3_RAW_IMAGE:-$BUILD_ROOT/Aurum-Pi3-Kernel-Trial-v${IMAGE_REVISION}-arm64.img}

if [ "$(id -u)" -ne 0 ]; then
  echo "diagnose-pi3-init.sh must run as root for a read-only loop mount." >&2
  exit 2
fi
for tool in file losetup mount mountpoint readelf readlink umount udevadm; do
  command -v "$tool" >/dev/null 2>&1 || { echo "$tool is required." >&2; exit 2; }
done

BUILD_ROOT=$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$BUILD_ROOT")
RAW_IMG=$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$RAW_IMG")
python3 - "$BUILD_ROOT" "$RAW_IMG" <<'PY'
from pathlib import Path
import sys

build, raw = (Path(value).resolve() for value in sys.argv[1:])
cache = (Path.home() / ".cache").resolve()
if cache not in build.parents or build not in raw.parents:
    raise SystemExit(f"Refusing diagnostic outside the root cache: {raw}")
PY

test -s "$RAW_IMG"
MOUNT_ROOT="$BUILD_ROOT/diagnose-init-root"
rm -rf -- "$MOUNT_ROOT"
mkdir -p "$MOUNT_ROOT"
LOOP_DEV=
cleanup() {
  set +e
  if mountpoint -q "$MOUNT_ROOT" 2>/dev/null; then umount "$MOUNT_ROOT"; fi
  if [ -n "$LOOP_DEV" ]; then losetup -d "$LOOP_DEV" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

LOOP_DEV=$(losetup --find --show --partscan --read-only "$RAW_IMG")
udevadm settle
test -b "${LOOP_DEV}p2"
mount -o ro "${LOOP_DEV}p2" "$MOUNT_ROOT"

printf '%s\n' '--- merged-/usr invariants ---'
ls -ld "$MOUNT_ROOT/lib" "$MOUNT_ROOT/bin" "$MOUNT_ROOT/sbin" "$MOUNT_ROOT/usr/lib"
for path in lib bin sbin; do
  if [ -L "$MOUNT_ROOT/$path" ]; then
    printf '%s -> %s\n' "/$path" "$(readlink "$MOUNT_ROOT/$path")"
  else
    printf '%s is not a symlink\n' "/$path"
  fi
done

printf '%s\n' '--- init executable contract ---'
for path in /sbin/init /bin/sh /usr/lib/systemd/systemd /lib/ld-linux-aarch64.so.1; do
  full="$MOUNT_ROOT$path"
  if [ -e "$full" ] || [ -L "$full" ]; then
    ls -l "$full"
    file -L "$full"
    if file -L "$full" | grep -q ELF; then
      readelf -l "$full" | grep -E 'interpreter|Requesting' || true
    fi
  else
    printf 'missing: %s\n' "$path"
  fi
done

printf '%s\n' '--- kernel modules ---'
find "$MOUNT_ROOT/usr/lib/modules" "$MOUNT_ROOT/lib/modules" -maxdepth 1 -mindepth 1 -type d -printf '%p\n' 2>/dev/null || true
