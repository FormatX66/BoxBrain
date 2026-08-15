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

# Prepare only the disposable QEMU copy as a post-provisioned runtime node.
# The published microSD image remains byte-for-byte unchanged.
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

test -s "$ROOT/opt/aurum/current/aurum_pi3_console.py"
test -d "$ROOT/opt/aurum/current/codelation/field"
sudo mkdir -p "$ROOT/etc/systemd/system"

# Full Raspberry Pi OS multi-user boot contains hardware services that QEMU's
# intentionally incomplete Pi model cannot satisfy. For the VM gate, use a
# scratch-only target that still proves the real kernel -> real SD rootfs ->
# systemd -> installed Aurum runtime handoff. It does not copy or execute a
# host-side Aurum program and it cannot make the published image pass falsely.
sudo tee "$ROOT/etc/systemd/system/aurum-virtual-lab.service" >/dev/null <<'EOF'
[Unit]
Description=Aurum Pi3 QEMU runtime verification
DefaultDependencies=no
After=local-fs.target
Requires=local-fs.target

[Service]
Type=simple
Environment=AURUM_ROOT=/opt/aurum/current
Environment=AURUM_RELEASE_ID_FROM_PATH=1
Environment=AURUM_READINESS_FILE=/run/aurum-pi3/virtual-lab-ready.json
ExecStart=/usr/bin/python3 /opt/aurum/current/aurum_pi3_console.py
StandardInput=tty-force
StandardOutput=tty
StandardError=tty
TTYPath=/dev/ttyAMA1
TTYReset=yes
TTYVHangup=no
Restart=no
EOF

sudo tee "$ROOT/etc/systemd/system/aurum-virtual-lab.target" >/dev/null <<'EOF'
[Unit]
Description=Aurum Pi3 virtual hardware verification target
Requires=local-fs.target aurum-virtual-lab.service
After=local-fs.target
AllowIsolate=yes
EOF

sync
sudo umount "$ROOT"
sudo losetup -d "$LOOP"
LOOP=""
echo "AURUM_PI3_QEMU_SCRATCH prepared=true machine_id=$MACHINE_ID target=aurum-virtual-lab.target"

# The physical image intentionally carries Raspberry Pi OS's `resize` argument
# and hardware-specific root/console aliases. Remove/replace those only in this
# synthetic QEMU command line and boot directly to the scratch-only Aurum target.
CMDLINE=""
for arg in $ORIGINAL_CMDLINE; do
  case "$arg" in
    resize|root=*|rootwait|rootdelay=*|console=*|systemd.unit=*) ;;
    *) CMDLINE="$CMDLINE $arg" ;;
  esac
done
CMDLINE="${CMDLINE# } root=/dev/mmcblk0p2 rootwait rootdelay=1 rw console=ttyAMA1,115200 systemd.unit=aurum-virtual-lab.target aurum.qemu=1"
printf 'AURUM_PI3_QEMU_CMDLINE %s\n' "$CMDLINE"

# Capture PL011 directly to a file; never bind guest input or the QEMU monitor
# to CI stdin. Stop as soon as the installed Aurum runtime proves readiness.
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
for _ in $(seq 1 210); do
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
  printf '%s\n' 'raspi3b-direct-kernel-real-microsd-rootfs-minimal-systemd-aurum-target' > "$MODE_FILE"
  echo 'AURUM_VIRTUAL_PI3_OK'
else
  echo "Pi3 QEMU did not reach Aurum readiness; qemu_status=$status" >&2
  exit 1
fi
