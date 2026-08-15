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

# Prepare only the disposable QEMU copy. The published microSD image remains
# byte-for-byte unchanged. This scratch init deliberately bypasses Raspberry Pi
# OS provisioning/system services that depend on hardware QEMU does not model;
# it still launches the installed Aurum runtime from the real image rootfs.
LOOP=$(sudo losetup --find --show --partscan "$WORK/aurum-pi3-qemu.img")
sudo udevadm settle
for _ in $(seq 1 20); do
  [ -b "${LOOP}p2" ] && break
  sleep 1
  sudo udevadm settle
done
test -b "${LOOP}p2"
sudo mount "${LOOP}p2" "$ROOT"

test -x "$ROOT/usr/bin/python3"
test -s "$ROOT/opt/aurum/current/aurum_pi3_console.py"
test -d "$ROOT/opt/aurum/current/codelation/field"
sudo mkdir -p "$ROOT/var/lib/aurum-pi3" "$ROOT/run/aurum-pi3"

sudo tee "$ROOT/sbin/aurum-vlab-init" >/dev/null <<'EOF'
#!/bin/sh
set -eu
mountpoint -q /proc || mount -t proc proc /proc
mountpoint -q /sys || mount -t sysfs sysfs /sys
mountpoint -q /run || mount -t tmpfs -o mode=755,nosuid,nodev tmpfs /run
mkdir -p /run/aurum-pi3 /var/lib/aurum-pi3
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PYTHONUNBUFFERED=1
export AURUM_ROOT=/opt/aurum/current
export AURUM_RELEASE_ID_FROM_PATH=1
export AURUM_READINESS_FILE=/run/aurum-pi3/virtual-lab-ready.json
exec /usr/bin/python3 /opt/aurum/current/aurum_pi3_console.py </dev/ttyAMA1 >/dev/ttyAMA1 2>&1
EOF
sudo chmod 0755 "$ROOT/sbin/aurum-vlab-init"

sync
sudo umount "$ROOT"
sudo losetup -d "$LOOP"
LOOP=""
echo 'AURUM_PI3_QEMU_SCRATCH prepared=true init=/sbin/aurum-vlab-init'

# Replace only physical-card provisioning/root/console arguments in the QEMU
# command line. The scratch init gives a bounded machine/runtime test:
# Pi3 CPU/kernel -> emulated SD -> real Aurum rootfs -> installed Python ->
# installed Codelation/Aurum runtime. Systemd wiring is verified separately by
# the image-structure gate and by physical-node evidence, not claimed here.
CMDLINE=""
for arg in $ORIGINAL_CMDLINE; do
  case "$arg" in
    resize|root=*|rootwait|rootdelay=*|console=*|systemd.unit=*|init=*) ;;
    *) CMDLINE="$CMDLINE $arg" ;;
  esac
done
CMDLINE="${CMDLINE# } root=/dev/mmcblk0p2 rootwait rootdelay=1 rw console=ttyAMA1,115200 init=/sbin/aurum-vlab-init aurum.qemu=1"
printf 'AURUM_PI3_QEMU_CMDLINE %s\n' "$CMDLINE"

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
  -no-reboot \
  </dev/null >/tmp/aurum-pi3-qemu-host.log 2>&1 &
QEMU_PID=$!

verified=0
for _ in $(seq 1 180); do
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
  printf '%s\n' 'raspi3b-direct-kernel-real-microsd-rootfs-installed-aurum-runtime' > "$MODE_FILE"
  echo 'AURUM_VIRTUAL_PI3_OK evidence=machine-runtime physical_hardware_evidence=not-implied'
else
  echo "Pi3 QEMU did not reach Aurum readiness; qemu_status=$status" >&2
  exit 1
fi
