#!/usr/bin/env bash
set -euo pipefail

RAW=${1:?usage: qemu-pi3-smoke.sh RAW_IMG LOG MODE_FILE}
LOG=${2:?usage: qemu-pi3-smoke.sh RAW_IMG LOG MODE_FILE}
MODE_FILE=${3:?usage: qemu-pi3-smoke.sh RAW_IMG LOG MODE_FILE}

WORK=$(mktemp -d)
ROOT="$WORK/root"
BOOT="$ROOT/boot/firmware"
LOOP=""
cleanup() {
  set +e
  mountpoint -q "$BOOT" && sudo umount "$BOOT"
  mountpoint -q "$ROOT" && sudo umount "$ROOT"
  [ -n "$LOOP" ] && sudo losetup -d "$LOOP" 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT INT TERM

mkdir -p "$ROOT"
LOOP=$(sudo losetup --find --show --partscan "$RAW")
sudo udevadm settle
for _ in $(seq 1 20); do
  [ -b "${LOOP}p1" ] && [ -b "${LOOP}p2" ] && break
  sleep 1
  sudo udevadm settle
done
test -b "${LOOP}p1"
test -b "${LOOP}p2"
sudo mount -o ro "${LOOP}p2" "$ROOT"
sudo mkdir -p "$BOOT"
sudo mount -o ro "${LOOP}p1" "$BOOT"

sudo cp "$BOOT/kernel8.img" "$WORK/kernel8.img"
sudo cp "$BOOT/bcm2710-rpi-3-b.dtb" "$WORK/bcm2710-rpi-3-b.dtb"
sudo cp "$BOOT/cmdline.txt" "$WORK/cmdline.txt"
sudo chown "$USER:$USER" "$WORK/kernel8.img" "$WORK/bcm2710-rpi-3-b.dtb" "$WORK/cmdline.txt"
ORIGINAL_CMDLINE=$(tr -d '\r\n' < "$WORK/cmdline.txt")

sudo umount "$BOOT"
sudo umount "$ROOT"
sudo losetup -d "$LOOP"
LOOP=""

# QEMU's SD model requires a power-of-two virtual card size. Keep the real
# Aurum partitions byte-for-byte and pad only unused space at the end.
cp --sparse=always "$RAW" "$WORK/aurum-pi3-qemu.img"
truncate -s 4G "$WORK/aurum-pi3-qemu.img"

# The Raspberry Pi OS cmdline uses PARTUUID and physical-Pi console aliases.
# For QEMU's raspi3b direct-kernel path, make those two machine contracts
# explicit while preserving every unrelated boot argument from the real image.
CMDLINE=""
for arg in $ORIGINAL_CMDLINE; do
  case "$arg" in
    root=*|rootwait|rootdelay=*|console=*) ;;
    *) CMDLINE="$CMDLINE $arg" ;;
  esac
done
CMDLINE="${CMDLINE# } root=/dev/mmcblk0p2 rootwait rootdelay=1 rw console=ttyAMA1,115200 aurum.qemu=1"
printf 'AURUM_PI3_QEMU_CMDLINE %s\n' "$CMDLINE"

# QEMU raspi3b exposes serial0 as ttyAMA1 with this device tree. Keep the QEMU
# monitor disabled: multiplexing the monitor onto stdio makes a non-interactive
# CI runner's stdin EOF terminate QEMU cleanly before systemd finishes booting.
set +e
timeout 180s qemu-system-aarch64 \
  -M raspi3b \
  -cpu cortex-a53 \
  -m 1G \
  -smp 4 \
  -kernel "$WORK/kernel8.img" \
  -dtb "$WORK/bcm2710-rpi-3-b.dtb" \
  -append "$CMDLINE" \
  -drive file="$WORK/aurum-pi3-qemu.img",format=raw,if=sd,index=0 \
  -display none \
  -serial stdio \
  -monitor none \
  -no-reboot \
  < /dev/null > "$LOG" 2>&1
status=$?
set -e
cat "$LOG"

if grep -F 'AURUM_PI3_READY' "$LOG" >/dev/null && grep -F 'selftest=ok' "$LOG" >/dev/null; then
  printf '%s\n' 'raspi3b-direct-kernel-with-real-microsd-rootfs' > "$MODE_FILE"
  echo 'AURUM_VIRTUAL_PI3_OK'
else
  echo "Pi3 QEMU did not reach Aurum readiness; qemu_status=$status" >&2
  exit 1
fi

if [ "$status" -ne 0 ] && [ "$status" -ne 124 ]; then
  echo "QEMU Pi3 exited unexpectedly with status $status" >&2
  exit "$status"
fi
