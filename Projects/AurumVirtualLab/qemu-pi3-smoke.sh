#!/usr/bin/env bash
set -euo pipefail

RAW=${1:?usage: qemu-pi3-smoke.sh RAW_IMG LOG MODE_FILE}
LOG=${2:?usage: qemu-pi3-smoke.sh RAW_IMG LOG MODE_FILE}
MODE_FILE=${3:?usage: qemu-pi3-smoke.sh RAW_IMG LOG MODE_FILE}

WORK=$(mktemp -d)
ROOT="$WORK/root"
BOOT="$ROOT/boot/firmware"
LOOP=""
QEMU_PID=""
cleanup() {
  set +e
  if [ -n "$QEMU_PID" ] && kill -0 "$QEMU_PID" 2>/dev/null; then
    kill "$QEMU_PID" 2>/dev/null || true
    wait "$QEMU_PID" 2>/dev/null || true
  fi
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

# QEMU's SD model requires a power-of-two virtual card size. Keep the shipped
# Aurum partitions byte-for-byte and pad only the disposable virtual medium.
cp --sparse=always "$RAW" "$WORK/aurum-pi3-qemu.img"
truncate -s 4G "$WORK/aurum-pi3-qemu.img"

# The physical image is intentionally pristine: Raspberry Pi OS expands the SD
# card and initializes machine identity on first hardware boot. The VM is a
# post-provision runtime test, so initialize *only the scratch copy*. A valid
# machine-id prevents systemd ConditionFirstBoot units from treating every CI
# VM as a brand-new installation. Nothing below mutates the published image.
LOOP=$(sudo losetup --find --show --partscan "$WORK/aurum-pi3-qemu.img")
sudo udevadm settle
for _ in $(seq 1 20); do
  [ -b "${LOOP}p2" ] && break
  sleep 1
  sudo udevadm settle
done
test -b "${LOOP}p2"
sudo mount "${LOOP}p2" "$ROOT"
MACHINE_ID=$(printf '%s' 'aurum-pi3-virtual-lab-v0' | sha256sum | cut -c1-32)
printf '%s\n' "$MACHINE_ID" | sudo tee "$ROOT/etc/machine-id" >/dev/null
if [ -e "$ROOT/var/lib/dbus/machine-id" ] && [ ! -L "$ROOT/var/lib/dbus/machine-id" ]; then
  printf '%s\n' "$MACHINE_ID" | sudo tee "$ROOT/var/lib/dbus/machine-id" >/dev/null
fi
sync
sudo umount "$ROOT"
sudo losetup -d "$LOOP"
LOOP=""
echo "AURUM_PI3_QEMU_MACHINE_ID initialized=true id=$MACHINE_ID"

# The physical Raspberry Pi image also carries the Raspberry Pi OS `resize`
# argument. Its firstboot path consumes that flag, grows the real card and
# force-reboots. Drop it only from this synthetic VM command line; the shipped
# image remains unchanged. Replace physical PARTUUID/serial aliases with QEMU
# contracts while preserving every unrelated kernel argument.
CMDLINE=""
for arg in $ORIGINAL_CMDLINE; do
  case "$arg" in
    resize|root=*|rootwait|rootdelay=*|console=*) ;;
    *) CMDLINE="$CMDLINE $arg" ;;
  esac
done
CMDLINE="${CMDLINE# } root=/dev/mmcblk0p2 rootwait rootdelay=1 rw console=ttyAMA1,115200 aurum.qemu=1"
printf 'AURUM_PI3_QEMU_CMDLINE %s\n' "$CMDLINE"

# Never bind the guest UART or monitor to CI stdin. Capture PL011 directly to a
# file, start QEMU asynchronously, and stop as soon as Aurum proves readiness.
# Guest-initiated reboot is intentionally allowed: Raspberry Pi provisioning
# and recovery units may request a reboot, and a real board would continue with
# the same SD card. The lab therefore observes across reboots instead of making
# a healthy reboot look like a VM failure.
: > "$LOG"
: > /tmp/aurum-pi3-qemu-host.log
qemu-system-aarch64 \
  -M raspi3b \
  -cpu cortex-a53 \
  -m 1G \
  -smp 4 \
  -kernel "$WORK/kernel8.img" \
  -dtb "$WORK/bcm2710-rpi-3-b.dtb" \
  -append "$CMDLINE" \
  -drive file="$WORK/aurum-pi3-qemu.img",format=raw,if=sd,index=0 \
  -display none \
  -serial "file:$LOG" \
  -monitor none \
  </dev/null >/tmp/aurum-pi3-qemu-host.log 2>&1 &
QEMU_PID=$!

verified=0
for _ in $(seq 1 150); do
  if grep -F 'AURUM_PI3_READY' "$LOG" >/dev/null 2>&1 && \
     grep -F 'selftest=ok' "$LOG" >/dev/null 2>&1; then
    verified=1
    break
  fi
  if ! kill -0 "$QEMU_PID" 2>/dev/null; then
    break
  fi
  sleep 1
done

set +e
if kill -0 "$QEMU_PID" 2>/dev/null; then
  kill "$QEMU_PID" 2>/dev/null || true
fi
wait "$QEMU_PID"
status=$?
set -e
QEMU_PID=""

cat /tmp/aurum-pi3-qemu-host.log || true
cat "$LOG"

if [ "$verified" -eq 1 ]; then
  printf '%s\n' 'raspi3b-direct-kernel-with-real-microsd-rootfs-post-provision-reboot-aware' > "$MODE_FILE"
  echo 'AURUM_VIRTUAL_PI3_OK'
else
  echo "Pi3 QEMU did not reach Aurum readiness; qemu_status=$status" >&2
  exit 1
fi
