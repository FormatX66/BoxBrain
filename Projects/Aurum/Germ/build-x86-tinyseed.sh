#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../../.." && pwd)
BUILD_ROOT=${AURUM_TINYSEED_BUILD_ROOT:-"$SCRIPT_DIR/.build-x86"}
DIST="$REPO_ROOT/dist"
IMAGE="$DIST/Aurum-TinySeed-amd64.iso"

if [ "$(id -u)" -ne 0 ]; then
  echo "build-x86-tinyseed.sh must run as root" >&2
  exit 2
fi
command -v lb >/dev/null 2>&1 || { echo "live-build is required" >&2; exit 2; }

rm -rf "$BUILD_ROOT"
mkdir -p "$BUILD_ROOT" "$DIST"
cd "$BUILD_ROOT"

lb config \
  --mode debian \
  --distribution bookworm \
  --architecture amd64 \
  --binary-image iso-hybrid \
  --system live \
  --debian-installer none \
  --archive-areas "main non-free-firmware" \
  --apt-recommends false \
  --security true \
  --updates true \
  --linux-packages linux-image \
  --linux-flavours amd64 \
  --bootloaders "syslinux grub-efi" \
  --uefi-secure-boot disable \
  --checksums sha256 \
  --memtest none \
  --bootappend-live "boot=live components edd=off quiet console=tty0 console=ttyS0,115200n8" \
  --iso-application "Aurum Tiny Seed" \
  --iso-publisher "FormatX66/BoxBrain" \
  --iso-volume "AURUM_TINY"

mkdir -p config/package-lists
cat > config/package-lists/tinyseed.list.chroot <<'EOF'
live-boot
systemd-sysv
udev
python3
git
ca-certificates
network-manager
iproute2
iputils-ping
iw
rfkill
wireless-regdb
firmware-iwlwifi
firmware-realtek
firmware-atheros
firmware-brcm80211
firmware-misc-nonfree
parted
rsync
dosfstools
e2fsprogs
util-linux
kbd
pciutils
usbutils
grub-efi-amd64-bin
grub-pc-bin
grub2-common
EOF

mkdir -p config/bootloaders/grub-pc
cat > config/bootloaders/grub-pc/grub.cfg <<'EOF'
set default=0
set timeout=1
menuentry "Aurum Tiny Seed" {
    linux @KERNEL_LIVE@ @APPEND_LIVE@
    initrd @INITRD_LIVE@
}
EOF

# Debian live-build's Syslinux/ISOLINUX default timeout is 0, which pauses
# indefinitely for a key press. Tiny Seed must boot unattended on legacy BIOS.
mkdir -p config/bootloaders/isolinux config/bootloaders/syslinux
cat > config/bootloaders/isolinux/isolinux.cfg <<'EOF'
include menu.cfg
default vesamenu.c32
prompt 0
timeout 10
EOF
cat > config/bootloaders/syslinux/syslinux.cfg <<'EOF'
include menu.cfg
default vesamenu.c32
prompt 0
timeout 10
EOF

GERM_DST=config/includes.chroot/usr/lib/aurum/germ
mkdir -p "$GERM_DST"
for name in GENETICS.json reseed.py guardian.py bridge.py germ_console.py machine.py network.py installer.py tinyseed.py bootstrap_console.py; do
  cp "$SCRIPT_DIR/$name" "$GERM_DST/$name"
done
chmod 0755 "$GERM_DST"/*.py
chmod 0644 "$GERM_DST/GENETICS.json"

mkdir -p config/includes.chroot/var/lib/aurum/slots/A/opt/aurum
cp "$SCRIPT_DIR/bootstrap_console.py" config/includes.chroot/var/lib/aurum/slots/A/opt/aurum/aurum_console.py
chmod 0755 config/includes.chroot/var/lib/aurum/slots/A/opt/aurum/aurum_console.py
mkdir -p config/includes.chroot/opt
ln -s /var/lib/aurum/slots/A/opt/aurum config/includes.chroot/opt/aurum
mkdir -p config/includes.chroot/var/lib/aurum/germ
cat > config/includes.chroot/var/lib/aurum/germ/slots.json <<'EOF'
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

mkdir -p config/includes.chroot/usr/sbin
cat > config/includes.chroot/usr/sbin/aurum-reseed <<'EOF'
#!/bin/sh
exec /usr/bin/python3 /usr/lib/aurum/germ/reseed.py "$@"
EOF
chmod 0755 config/includes.chroot/usr/sbin/aurum-reseed

SYSTEMD=config/includes.chroot/etc/systemd/system
WANTS=$SYSTEMD/multi-user.target.wants
mkdir -p "$WANTS"
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
ExecStart=/bin/sh -c 'test -s /usr/lib/aurum/germ/GENETICS.json && test -x /usr/lib/aurum/germ/reseed.py && echo AURUM_TINYSEED_READY > /dev/console; if [ -c /dev/ttyS0 ]; then echo AURUM_TINYSEED_READY > /dev/ttyS0; fi'
[Install]
WantedBy=multi-user.target
EOF
for unit in aurum-germ-preflight.service aurum-germ-health.service aurum-tinyseed.service aurum-tinyseed-smoke.service; do
  ln -s "../$unit" "$WANTS/$unit"
done
ln -s /lib/systemd/system/NetworkManager.service "$WANTS/NetworkManager.service"
ln -s /dev/null "$SYSTEMD/getty@tty1.service"

mkdir -p config/includes.chroot/etc
printf '%s\n' aurum-tinyseed > config/includes.chroot/etc/hostname
cat > config/includes.chroot/etc/motd <<'EOF'
Aurum Tiny Seed
Git stores the genetics. Tiny Seed carries the germ. The machine grows Aurum.
EOF

mkdir -p config/hooks/live
cat > config/hooks/live/010-tinyseed.hook.chroot <<'EOF'
#!/bin/sh
set -eu
chmod 0755 /usr/lib/aurum/germ/*.py /usr/sbin/aurum-reseed
EOF
chmod 0755 config/hooks/live/010-tinyseed.hook.chroot

lb build
ISO=$(find . -maxdepth 1 -type f \( -name 'live-image-amd64*.hybrid.iso' -o -name 'live-image-amd64*.iso' \) | head -n 1)
[ -n "${ISO:-}" ] && [ -s "$ISO" ] || { echo "Tiny Seed build produced no ISO" >&2; exit 1; }
cp "$ISO" "$IMAGE"
(
  cd "$REPO_ROOT"
  sha256sum dist/Aurum-TinySeed-amd64.iso > dist/Aurum-TinySeed-amd64.iso.sha256
)
echo "AURUM_TINYSEED_X86_BUILD_OK image=$IMAGE"
