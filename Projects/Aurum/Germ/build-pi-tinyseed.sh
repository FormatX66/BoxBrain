#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../../.." && pwd)
BUILD_ROOT=${AURUM_TINYSEED_PI_BUILD_ROOT:-"$SCRIPT_DIR/.build-pi"}
DIST="$REPO_ROOT/dist"
IMAGE_STEM="Aurum-TinySeed-Pi-arm64"
RAW="$BUILD_ROOT/$IMAGE_STEM.img"
OUT="$DIST/$IMAGE_STEM.img.xz"
OUT_SHA="$OUT.sha256"
BASE_XZ="$BUILD_ROOT/raspios-lite-arm64.img.xz"
BASE_URL="https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-2026-06-19/2026-06-18-raspios-trixie-arm64-lite.img.xz"
BASE_SHA256="acff736ca7945e3b305f07cda4abdb870910e12634991da69783611756e381b3"

[ "$(id -u)" -eq 0 ] || { echo "build-pi-tinyseed.sh must run as root" >&2; exit 2; }
for cmd in curl xz sha256sum losetup mount umount udevadm rsync; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "Missing $cmd" >&2; exit 2; }
done
QEMU_STATIC=${QEMU_AARCH64_STATIC:-$(command -v qemu-aarch64-static || true)}
[ -n "$QEMU_STATIC" ] || { echo "qemu-aarch64-static is required to prepare the ARM64 root" >&2; exit 2; }

rm -rf "$BUILD_ROOT"
mkdir -p "$BUILD_ROOT" "$DIST"
cleanup() {
  set +e
  for p in "${ROOT_MNT:-}/run" "${ROOT_MNT:-}/sys" "${ROOT_MNT:-}/proc" "${ROOT_MNT:-}/dev" "${BOOT_MNT:-}" "${ROOT_MNT:-}"; do
    [ -n "$p" ] && mountpoint -q "$p" 2>/dev/null && umount -l "$p" 2>/dev/null || true
  done
  [ -n "${LOOP_DEV:-}" ] && losetup -d "$LOOP_DEV" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

curl -L --fail --retry 5 --retry-delay 2 -o "$BASE_XZ" "$BASE_URL"
printf '%s  %s\n' "$BASE_SHA256" "$BASE_XZ" | sha256sum -c -
xz -dc "$BASE_XZ" > "$RAW"

LOOP_DEV=$(losetup --find --show --partscan "$RAW")
udevadm settle
ROOT_PART="${LOOP_DEV}p2"
BOOT_PART="${LOOP_DEV}p1"
[ -b "$ROOT_PART" ] && [ -b "$BOOT_PART" ] || { echo "Pi base partitions missing" >&2; exit 1; }
ROOT_MNT="$BUILD_ROOT/root"
BOOT_MNT="$ROOT_MNT/boot/firmware"
mkdir -p "$ROOT_MNT"
mount "$ROOT_PART" "$ROOT_MNT"
mkdir -p "$BOOT_MNT"
mount "$BOOT_PART" "$BOOT_MNT"

install -m 0755 "$QEMU_STATIC" "$ROOT_MNT/usr/bin/qemu-aarch64-static"
rm -f "$ROOT_MNT/etc/resolv.conf"
printf '%s\n' 'nameserver 1.1.1.1' > "$ROOT_MNT/etc/resolv.conf"
for rel in dev proc sys run; do mkdir -p "$ROOT_MNT/$rel"; done
mount --bind /dev "$ROOT_MNT/dev"
mount -t proc proc "$ROOT_MNT/proc"
mount -t sysfs sysfs "$ROOT_MNT/sys"
mount --bind /run "$ROOT_MNT/run"
chroot "$ROOT_MNT" /usr/bin/qemu-aarch64-static /bin/sh -lc '
  set -eu
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    git ca-certificates openssl network-manager python3 rsync parted dosfstools e2fsprogs util-linux
  apt-get clean
  rm -rf /var/lib/apt/lists/*
'
umount "$ROOT_MNT/run"
umount "$ROOT_MNT/sys"
umount "$ROOT_MNT/proc"
umount "$ROOT_MNT/dev"
rm -f "$ROOT_MNT/usr/bin/qemu-aarch64-static"

GERM_DST="$ROOT_MNT/usr/lib/aurum/germ"
mkdir -p "$GERM_DST"
for name in GENETICS.json reseed.py guardian.py bridge.py germ_console.py machine.py network.py installer.py tinyseed.py bootstrap_console.py proof.py rollback_drill.py recovery_control.py recovery_poller.py; do
  install -m 0755 "$SCRIPT_DIR/$name" "$GERM_DST/$name"
done
chmod 0644 "$GERM_DST/GENETICS.json"

RECOVERY_SRC="$REPO_ROOT/Projects/Aurum/Recovery"
mkdir -p "$ROOT_MNT/etc/aurum"
install -m 0644 "$RECOVERY_SRC/trusted-refs.json" "$ROOT_MNT/etc/aurum/recovery-trusted-refs.json"
if [ -f "$RECOVERY_SRC/authority-public.pem" ]; then
  install -m 0644 "$RECOVERY_SRC/authority-public.pem" "$ROOT_MNT/etc/aurum/recovery-authority.pem"
fi

mkdir -p "$ROOT_MNT/var/lib/aurum/slots/A/opt/aurum" "$ROOT_MNT/var/lib/aurum/germ" "$ROOT_MNT/opt"
install -m 0755 "$SCRIPT_DIR/bootstrap_console.py" "$ROOT_MNT/var/lib/aurum/slots/A/opt/aurum/aurum_console.py"
rm -rf "$ROOT_MNT/opt/aurum"
ln -s /var/lib/aurum/slots/A/opt/aurum "$ROOT_MNT/opt/aurum"
cat > "$ROOT_MNT/var/lib/aurum/germ/slots.json" <<'EOF'
{
  "schema": "aurum-germ-slots-v1",
  "active": "A",
  "lkg": "A",
  "trial": null,
  "trial_boots": 0,
  "quarantined": [],
  "last_result": "tiny-seed-bootstrap"
}
EOF
mkdir -p "$ROOT_MNT/usr/sbin"
cat > "$ROOT_MNT/usr/sbin/aurum-reseed" <<'EOF'
#!/bin/sh
exec /usr/bin/python3 /usr/lib/aurum/germ/reseed.py "$@"
EOF
cat > "$ROOT_MNT/usr/sbin/aurum-rollback-drill" <<'EOF'
#!/bin/sh
exec /usr/bin/python3 /usr/lib/aurum/germ/rollback_drill.py "$@"
EOF
cat > "$ROOT_MNT/usr/sbin/aurum-recovery-poll" <<'EOF'
#!/bin/sh
exec /usr/bin/python3 /usr/lib/aurum/germ/recovery_poller.py "$@"
EOF
chmod 0755 "$ROOT_MNT/usr/sbin/aurum-reseed" "$ROOT_MNT/usr/sbin/aurum-rollback-drill" "$ROOT_MNT/usr/sbin/aurum-recovery-poll"

SYSTEMD="$ROOT_MNT/etc/systemd/system"
WANTS="$SYSTEMD/multi-user.target.wants"
TIMERS="$SYSTEMD/timers.target.wants"
mkdir -p "$WANTS" "$TIMERS"
cat > "$SYSTEMD/aurum-germ-preflight.service" <<'EOF'
[Unit]
Description=Aurum protected germ preflight
After=local-fs.target
Before=aurum-tinyseed.service
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/lib/aurum/germ/guardian.py preflight --reboot-on-rollback
[Install]
WantedBy=multi-user.target
EOF
cat > "$SYSTEMD/aurum-germ-health.service" <<'EOF'
[Unit]
Description=Aurum protected germ candidate health gate
After=aurum-germ-preflight.service
[Service]
Type=oneshot
ExecStartPre=/bin/sleep 8
ExecStart=/usr/bin/python3 /usr/lib/aurum/germ/guardian.py health-check --reboot-on-rollback
[Install]
WantedBy=multi-user.target
EOF
cat > "$SYSTEMD/aurum-tinyseed.service" <<'EOF'
[Unit]
Description=Aurum Tiny Seed setup
After=NetworkManager.service aurum-germ-preflight.service
Wants=NetworkManager.service
Conflicts=getty@tty1.service
[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/lib/aurum/germ/tinyseed.py
StandardInput=tty-force
StandardOutput=tty
StandardError=tty
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes
Restart=on-failure
RestartSec=2
[Install]
WantedBy=multi-user.target
EOF
cat > "$SYSTEMD/aurum-tinyseed-smoke.service" <<'EOF'
[Unit]
Description=Aurum Tiny Seed smoke marker
After=local-fs.target
[Service]
Type=oneshot
ExecStart=/bin/sh -c 'test -s /usr/lib/aurum/germ/GENETICS.json && echo AURUM_TINYSEED_READY > /dev/console; if [ -c /dev/serial0 ]; then echo AURUM_TINYSEED_READY > /dev/serial0; fi'
[Install]
WantedBy=multi-user.target
EOF
cat > "$SYSTEMD/aurum-boot-proof.service" <<'EOF'
[Unit]
Description=Aurum non-secret boot proof receipt
After=local-fs.target aurum-germ-preflight.service
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/lib/aurum/germ/proof.py
StandardOutput=journal+console
StandardError=journal+console
[Install]
WantedBy=multi-user.target
EOF
cat > "$SYSTEMD/aurum-recovery-poll.service" <<'EOF'
[Unit]
Description=Aurum signed remote recovery desired-state check
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/lib/aurum/germ/recovery_poller.py
SuccessExitStatus=2
NoNewPrivileges=true
EOF
cat > "$SYSTEMD/aurum-recovery-poll.timer" <<'EOF'
[Unit]
Description=Periodically check Aurum signed recovery desired state
[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
RandomizedDelaySec=30s
Persistent=true
Unit=aurum-recovery-poll.service
[Install]
WantedBy=timers.target
EOF
for unit in aurum-germ-preflight.service aurum-germ-health.service aurum-tinyseed.service aurum-tinyseed-smoke.service aurum-boot-proof.service; do
  ln -sfn "../$unit" "$WANTS/$unit"
done
ln -sfn "../aurum-recovery-poll.timer" "$TIMERS/aurum-recovery-poll.timer"
ln -sfn /lib/systemd/system/NetworkManager.service "$WANTS/NetworkManager.service"
ln -sfn /dev/null "$SYSTEMD/getty@tty1.service"

printf '%s\n' aurum-tinyseed > "$ROOT_MNT/etc/hostname"
CONFIG="$BOOT_MNT/config.txt"
CMDLINE="$BOOT_MNT/cmdline.txt"
[ -f "$CONFIG" ] && [ -f "$CMDLINE" ] || { echo "Pi boot files missing" >&2; exit 1; }
if ! grep -q '^# Aurum Tiny Seed$' "$CONFIG"; then
  cat >> "$CONFIG" <<'EOF'

# Aurum Tiny Seed
[all]
arm_64bit=1
enable_uart=1
EOF
fi
LINE=$(tr -d '\r\n' < "$CMDLINE")
case " $LINE " in *" console=serial0,115200 "*) : ;; *) LINE="$LINE console=serial0,115200" ;; esac
case " $LINE " in *" aurum.tinyseed=1 "*) : ;; *) LINE="$LINE aurum.tinyseed=1" ;; esac
printf '%s\n' "$LINE" > "$CMDLINE"

sync
umount "$BOOT_MNT"
umount "$ROOT_MNT"
losetup -d "$LOOP_DEV"
LOOP_DEV=""
XZ_OPT=-3 xz -T0 -c "$RAW" > "$OUT"
(
  cd "$DIST"
  sha256sum "$(basename "$OUT")" > "$(basename "$OUT_SHA")"
)
echo "AURUM_TINYSEED_PI_BUILD_OK image=$OUT"
