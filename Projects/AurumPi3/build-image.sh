#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
BUILD_ROOT="$SCRIPT_DIR/.build"
DIST="$REPO_ROOT/dist"
IMAGE_STEM="Aurum-Pi3-v0.01-arm64"
RAW_IMG="$BUILD_ROOT/$IMAGE_STEM.img"
OUT_XZ="$DIST/$IMAGE_STEM.img.xz"
OUT_SHA="$OUT_XZ.sha256"
OUT_MANIFEST="$DIST/$IMAGE_STEM.manifest.json"
BASE_XZ="$BUILD_ROOT/raspios-lite-arm64.img.xz"
BASE_URL="https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-2026-06-19/2026-06-18-raspios-trixie-arm64-lite.img.xz"
BASE_SHA256="acff736ca7945e3b305f07cda4abdb870910e12634991da69783611756e381b3"

if [ "$(id -u)" -ne 0 ]; then
  echo "build-image.sh must run as root for loop/mount operations." >&2
  exit 2
fi
for cmd in curl xz sha256sum losetup mount umount udevadm; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "Missing required command: $cmd" >&2; exit 2; }
done
if [ ! -d "$REPO_ROOT/Projects/Codelation" ]; then
  echo "Projects/Codelation is missing." >&2
  exit 2
fi
if [ ! -f "$SCRIPT_DIR/aurum_pi3_console.py" ]; then
  echo "Aurum Pi3 console source is missing." >&2
  exit 2
fi
if [ ! -f "$SCRIPT_DIR/aurum_updater.py" ] || [ ! -d "$SCRIPT_DIR/systemd" ]; then
  echo "Aurum Pi3 updater or systemd units are missing." >&2
  exit 2
fi

rm -rf "$BUILD_ROOT"
mkdir -p "$BUILD_ROOT" "$DIST"
rm -f "$OUT_XZ" "$OUT_SHA" "$OUT_MANIFEST"

cleanup() {
  set +e
  if [ -n "${BOOT_MNT:-}" ] && mountpoint -q "$BOOT_MNT" 2>/dev/null; then umount "$BOOT_MNT"; fi
  if [ -n "${ROOT_MNT:-}" ] && mountpoint -q "$ROOT_MNT" 2>/dev/null; then umount "$ROOT_MNT"; fi
  if [ -n "${LOOP_DEV:-}" ]; then losetup -d "$LOOP_DEV" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

echo "AURUM_PI3_BASE_FETCH url=$BASE_URL"
curl -L --fail --retry 5 --retry-delay 2 -o "$BASE_XZ" "$BASE_URL"
printf '%s  %s\n' "$BASE_SHA256" "$BASE_XZ" | sha256sum -c -

xz -dc "$BASE_XZ" > "$RAW_IMG"
LOOP_DEV=$(losetup --find --show --partscan "$RAW_IMG")
udevadm settle
ROOT_PART="${LOOP_DEV}p2"
BOOT_PART="${LOOP_DEV}p1"
for _ in $(seq 1 20); do
  [ -b "$ROOT_PART" ] && [ -b "$BOOT_PART" ] && break
  sleep 1
  udevadm settle
done
[ -b "$ROOT_PART" ] || { echo "Root partition not found: $ROOT_PART" >&2; exit 1; }
[ -b "$BOOT_PART" ] || { echo "Boot partition not found: $BOOT_PART" >&2; exit 1; }

ROOT_MNT="$BUILD_ROOT/root"
BOOT_MNT="$ROOT_MNT/boot/firmware"
mkdir -p "$ROOT_MNT"
mount "$ROOT_PART" "$ROOT_MNT"
mkdir -p "$BOOT_MNT"
mount "$BOOT_PART" "$BOOT_MNT"

BOOTSTRAP_RELEASE="$ROOT_MNT/opt/aurum/releases/0.01-bootstrap"
mkdir -p "$BOOTSTRAP_RELEASE" "$ROOT_MNT/opt/aurum/updater"
install -m 0755 "$SCRIPT_DIR/aurum_pi3_console.py" "$BOOTSTRAP_RELEASE/aurum_pi3_console.py"
install -m 0755 "$SCRIPT_DIR/aurum_updater.py" "$ROOT_MNT/opt/aurum/updater/aurum_updater.py"
install -d -m 0700 "$ROOT_MNT/var/lib/aurum-pi3"
install -d -m 0700 "$ROOT_MNT/var/lib/aurum-updater"
cp -a "$REPO_ROOT/Projects/Codelation" "$BOOTSTRAP_RELEASE/codelation"
find "$BOOTSTRAP_RELEASE/codelation" -type f -name '*.py' -exec chmod 0644 {} +
cat > "$BOOTSTRAP_RELEASE/RELEASE.json" <<'EOF'
{
  "application_layer_only": true,
  "architecture": "arm64",
  "includes_boot_firmware": false,
  "includes_kernel": false,
  "release_id": "0.01-bootstrap",
  "schema": "aurum-runtime-release-v1",
  "target": "raspberry-pi-3",
  "version": "0.01"
}
EOF
ln -sfn releases/0.01-bootstrap "$ROOT_MNT/opt/aurum/current"

SYSTEMD="$ROOT_MNT/etc/systemd/system"
mkdir -p "$SYSTEMD/multi-user.target.wants"
for unit in \
  aurum-pi3-console.service \
  aurum-pi3-serial.service \
  aurum-pi3-update.service \
  aurum-pi3-update-recovery.service
do
  install -m 0644 "$SCRIPT_DIR/systemd/$unit" "$SYSTEMD/$unit"
done

ln -sfn ../aurum-pi3-console.service "$SYSTEMD/multi-user.target.wants/aurum-pi3-console.service"
ln -sfn ../aurum-pi3-serial.service "$SYSTEMD/multi-user.target.wants/aurum-pi3-serial.service"
ln -sfn ../aurum-pi3-update-recovery.service "$SYSTEMD/multi-user.target.wants/aurum-pi3-update-recovery.service"
ln -sfn /dev/null "$SYSTEMD/getty@tty1.service"
ln -sfn /dev/null "$SYSTEMD/serial-getty@serial0.service"
ln -sfn /dev/null "$SYSTEMD/serial-getty@ttyAMA0.service"

printf '%s\n' 'aurum-pi3' > "$ROOT_MNT/etc/hostname"
if grep -q '^127\.0\.1\.1' "$ROOT_MNT/etc/hosts"; then
  sed -i 's/^127\.0\.1\.1.*/127.0.1.1\taurum-pi3/' "$ROOT_MNT/etc/hosts"
else
  printf '%s\n' '127.0.1.1\taurum-pi3' >> "$ROOT_MNT/etc/hosts"
fi
cat > "$ROOT_MNT/etc/motd" <<'EOF'
Aurum Pi3 v0.01
Raspberry Pi OS is present only as the temporary Pi hardware compatibility substrate.
The exposed operator surface is the bounded Aurum console; no arbitrary shell is offered by Aurum.
EOF

CONFIG_TXT="$BOOT_MNT/config.txt"
CMDLINE_TXT="$BOOT_MNT/cmdline.txt"
[ -f "$CONFIG_TXT" ] || { echo "Raspberry Pi config.txt missing from base image." >&2; exit 1; }
[ -f "$CMDLINE_TXT" ] || { echo "Raspberry Pi cmdline.txt missing from base image." >&2; exit 1; }
if ! grep -q '^# Aurum Pi3 v0.01$' "$CONFIG_TXT"; then
  cat >> "$CONFIG_TXT" <<'EOF'

# Aurum Pi3 v0.01
[all]
arm_64bit=1
enable_uart=1
EOF
fi
CMDLINE=$(tr -d '\r\n' < "$CMDLINE_TXT")
case " $CMDLINE " in
  *" console=serial0,115200 "*) : ;;
  *) CMDLINE="$CMDLINE console=serial0,115200" ;;
esac
case " $CMDLINE " in
  *" aurum.pi3=1 "*) : ;;
  *) CMDLINE="$CMDLINE aurum.pi3=1" ;;
esac
printf '%s\n' "$CMDLINE" > "$CMDLINE_TXT"

sync
umount "$BOOT_MNT"
umount "$ROOT_MNT"
losetup -d "$LOOP_DEV"
LOOP_DEV=""

RAW_SHA=$(sha256sum "$RAW_IMG" | awk '{print $1}')
RAW_BYTES=$(stat -c '%s' "$RAW_IMG")
XZ_OPT=-3 xz -T0 -c "$RAW_IMG" > "$OUT_XZ"
(
  cd "$DIST"
  sha256sum "$(basename "$OUT_XZ")" > "$(basename "$OUT_SHA")"
)
XZ_SHA=$(sha256sum "$OUT_XZ" | awk '{print $1}')
XZ_BYTES=$(stat -c '%s' "$OUT_XZ")
cat > "$OUT_MANIFEST" <<EOF
{
  "schema": "aurum-pi3-image-manifest-v0",
  "version": "0.01",
  "target": "raspberry-pi-3",
  "architecture": "arm64",
  "media": "microSD/raw-disk-image",
  "base": {
    "name": "Raspberry Pi OS Lite 64-bit",
    "release": "2026-06-18",
    "debian": "trixie",
    "url": "$BASE_URL",
    "sha256": "$BASE_SHA256"
  },
  "output": {
    "image": "$(basename "$OUT_XZ")",
    "compressed_sha256": "$XZ_SHA",
    "compressed_bytes": $XZ_BYTES,
    "raw_sha256": "$RAW_SHA",
    "raw_bytes": $RAW_BYTES
  },
  "verification": {
    "upstream_checksum": true,
    "partition_structure": "pending-ci-static-verification",
    "pi3_physical_boot": false
  }
}
EOF

echo "AURUM_PI3_IMAGE_READY raw=$RAW_IMG compressed=$OUT_XZ sha256=$XZ_SHA"
ls -lh "$RAW_IMG" "$OUT_XZ" "$OUT_SHA" "$OUT_MANIFEST"
